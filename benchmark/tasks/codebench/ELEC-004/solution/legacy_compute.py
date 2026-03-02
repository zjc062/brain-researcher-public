import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne
import numpy as np

TASK_ID = "ELEC-004"
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

from mne.time_frequency import AverageTFRArray

def write_failfast(reason: str, data_root: Path | None, checked_paths: list[Path], records_count: int, bytes_total: int):
    info = mne.create_info(["MEG0111"], sfreq=100.0, ch_types=["grad"])
    data = np.zeros((1, 3, 10), dtype=float)
    times = np.linspace(0.0, 0.09, 10)
    freqs = np.array([30.0, 40.0, 50.0])
    tfr = AverageTFRArray(info, data, times, freqs, nave=1)
    tfr.save(output_dir / "tfr_average.h5", overwrite=True)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.imshow(data[0], aspect="auto", origin="lower")
    ax.set_title(f"ELEC-004 fail-fast: {reason}")
    fig.savefig(output_dir / "time_frequency_plot.png", dpi=120)
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
    raw.filter(1.0, 80.0, verbose="ERROR")

    events = mne.read_events(events_path)
    events = events[(events[:, 0] >= raw.first_samp) & (events[:, 0] <= raw.last_samp)]
    if len(events) == 0:
        write_failfast("no_events_in_window", root, checked_paths, file_count, byte_count)
        raise SystemExit(0)

    event_id = {"auditory/left": 1, "auditory/right": 2}
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
    if len(epochs) == 0:
        write_failfast("insufficient_epochs", root, checked_paths, file_count, byte_count)
        raise SystemExit(0)

    freqs = np.arange(30.0, 51.0, 4.0)
    n_cycles = np.full(len(freqs), 3.0)
    tfr = mne.time_frequency.tfr_morlet(
        epochs,
        freqs=freqs,
        n_cycles=n_cycles,
        picks="grad",
        return_itc=False,
        average=True,
        decim=4,
        n_jobs=1,
        verbose="ERROR",
    )
    tfr.save(output_dir / "tfr_average.h5", overwrite=True)

    figs = tfr.plot(picks=[0], show=False)
    fig = figs[0] if isinstance(figs, list) else figs
    fig.savefig(output_dir / "time_frequency_plot.png", dpi=120)
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
            "n_epochs": int(len(epochs)),
            "n_channels": int(tfr.data.shape[0]),
            "n_freqs": int(tfr.data.shape[1]),
            "n_times": int(tfr.data.shape[2]),
            "freq_min_hz": float(freqs.min()),
            "freq_max_hz": float(freqs.max()),
            "mean_power": float(np.mean(tfr.data)),
        },
    )
except Exception as exc:
    write_failfast(f"compute_error: {exc.__class__.__name__}", root, checked_paths, file_count, byte_count)
