import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne
import numpy as np

TASK_ID = "ELEC-003"
DATASET_SOURCE = "Provided"
DATASET_ID = "mne_sample_dataset"

output_dir = Path(os.environ["OUTPUT_DIR"]).resolve()
task_dir = Path(os.environ["TASK_DIR"]).resolve()


def candidate_input_dirs(dataset_id: str) -> list[Path]:
    env_input = os.environ.get("INPUT_DIR", "").strip()
    candidates = []
    if env_input:
        candidates.append(Path(env_input))
        candidates.append(Path(env_input) / dataset_id)

    candidates.extend(
        [
            Path("/task/cache") / dataset_id,
            Path("/task/cache"),
            Path("/task/input") / dataset_id,
            Path("/task/input"),
            Path("/app/input") / dataset_id,
            Path("/app/input"),
            task_dir / "input",
            task_dir / "data",
        ]
    )

    uniq = []
    seen = set()
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def resolve_input_root(dataset_id: str):
    checked = candidate_input_dirs(dataset_id)
    existing = [p for p in checked if p.exists() and p.is_dir()]
    if not existing:
        return None, checked, [], 0, 0

    best_root = None
    best_files = []
    for root in existing:
        files = [p for p in root.rglob("*") if p.is_file()]
        if len(files) > len(best_files):
            best_root = root
            best_files = files

    if best_root is None:
        return None, checked, [], 0, 0

    file_count = len(best_files)
    byte_count = int(sum(p.stat().st_size for p in best_files))
    return best_root, checked, best_files, file_count, byte_count


def find_file(files: list[Path], name: str):
    matches = [p for p in files if p.name == name]
    if not matches:
        return None
    matches.sort(key=lambda p: len(p.parts))
    return matches[0]


def write_run_metadata(status: str, reason: str, data_root: Path | None, checked_paths: list[Path], records_count: int, bytes_total: int, extras: dict | None = None):
    payload = {
        "task_id": TASK_ID,
        "dataset_source": DATASET_SOURCE,
        "dataset_id": DATASET_ID,
        "status": status,
        "reason": reason,
        "data_root": str(data_root) if data_root else "",
        "checked_paths": [str(p) for p in checked_paths],
        "records_count": int(records_count),
        "bytes_total": int(bytes_total),
    }
    if extras:
        payload.update(extras)
    (output_dir / "run_metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

def write_failfast(reason: str, data_root: Path | None, checked_paths: list[Path], records_count: int, bytes_total: int):
    info = mne.create_info(["MEG0111", "MEG0112"], sfreq=1000.0, ch_types=["grad", "grad"])
    ev = mne.EvokedArray(np.zeros((2, 200), dtype=float), info, tmin=-0.2, nave=1)
    mne.write_evokeds(output_dir / "auditory_evoked.fif", [ev], overwrite=True)
    mne.write_evokeds(output_dir / "visual_evoked.fif", [ev], overwrite=True)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(ev.times, ev.data[0], label="baseline")
    ax.legend()
    ax.set_title(f"ELEC-003 fail-fast: {reason}")
    fig.savefig(output_dir / "evoked_plot.png", dpi=120)
    plt.close(fig)

    write_run_metadata("failed_precondition", reason, data_root, checked_paths, records_count, bytes_total)


root, checked_paths, files, file_count, byte_count = resolve_input_root(DATASET_ID)
if root is None or file_count == 0:
    write_failfast("missing_input_dir_or_empty", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)

raw_path = find_file(files, "sample_audvis_raw.fif")
events_path = find_file(files, "sample_audvis_raw-eve.fif")
if raw_path is None:
    write_failfast("missing_raw_fif", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)
if events_path is None:
    write_failfast("missing_events_fif", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)

try:
    raw = mne.io.read_raw_fif(raw_path, preload=True, verbose="ERROR")
    raw.crop(0.0, min(60.0, raw.times[-1]))
    raw.pick(["meg", "eog", "stim"], exclude=[])
    raw.filter(1.0, 40.0, verbose="ERROR")

    events = mne.read_events(events_path)
    events = events[(events[:, 0] >= raw.first_samp) & (events[:, 0] <= raw.last_samp)]
    if len(events) == 0:
        write_failfast("no_events_in_window", root, checked_paths, file_count, byte_count)
        raise SystemExit(0)

    event_id = {
        "auditory/left": 1,
        "auditory/right": 2,
        "visual/left": 3,
        "visual/right": 4,
    }
    epochs = mne.Epochs(
        raw,
        events,
        event_id=event_id,
        tmin=-0.2,
        tmax=0.5,
        baseline=(None, 0.0),
        preload=True,
        reject_by_annotation=True,
        verbose="ERROR",
    )

    aud_epochs = epochs[["auditory/left", "auditory/right"]]
    vis_epochs = epochs[["visual/left", "visual/right"]]
    if len(aud_epochs) == 0 or len(vis_epochs) == 0:
        write_failfast("insufficient_event_classes", root, checked_paths, file_count, byte_count)
        raise SystemExit(0)

    auditory = aud_epochs.average()
    visual = vis_epochs.average()
    mne.write_evokeds(output_dir / "auditory_evoked.fif", [auditory], overwrite=True)
    mne.write_evokeds(output_dir / "visual_evoked.fif", [visual], overwrite=True)

    figs = mne.viz.plot_compare_evokeds({"auditory": auditory, "visual": visual}, combine="mean", show=False)
    fig = figs[0] if isinstance(figs, list) else figs
    fig.savefig(output_dir / "evoked_plot.png", dpi=120)
    plt.close("all")

    write_run_metadata(
        "ok",
        "computed",
        root,
        checked_paths,
        file_count,
        byte_count,
        extras={
            "raw_path": str(raw_path),
            "events_path": str(events_path),
            "n_events_in_window": int(len(events)),
            "n_auditory_epochs": int(len(aud_epochs)),
            "n_visual_epochs": int(len(vis_epochs)),
            "n_channels": int(len(auditory.ch_names)),
            "n_times": int(auditory.data.shape[1]),
        },
    )
except Exception as exc:
    write_failfast(f"compute_error: {exc.__class__.__name__}", root, checked_paths, file_count, byte_count)
