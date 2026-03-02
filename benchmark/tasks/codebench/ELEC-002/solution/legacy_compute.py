import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne
import numpy as np

TASK_ID = "ELEC-002"
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
    info = mne.create_info(["MEG0111", "MEG0112", "EOG061"], sfreq=200.0, ch_types=["grad", "grad", "eog"])
    t = np.linspace(0.0, 10.0, 2000, dtype=float)
    sig = np.vstack(
        [
            1e-6 * np.sin(2.0 * np.pi * 7.0 * t),
            1e-6 * np.cos(2.0 * np.pi * 9.0 * t),
            5e-7 * np.sin(2.0 * np.pi * 1.0 * t),
        ]
    )
    raw = mne.io.RawArray(sig, info, verbose="ERROR")
    ica = mne.preprocessing.ICA(n_components=2, random_state=97, max_iter="auto", method="fastica")
    ica.fit(raw.copy().pick("meg"), verbose="ERROR")
    ica.save(output_dir / "ica_solution.fif", overwrite=True)

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(np.linspace(0.0, 1.0, 50), np.zeros(50))
    ax.set_title(f"ELEC-002 fail-fast: {reason}")
    fig.savefig(output_dir / "component_topographies.png", dpi=120)
    plt.close(fig)

    write_run_metadata("failed_precondition", reason, data_root, checked_paths, records_count, bytes_total)


root, checked_paths, files, file_count, byte_count = resolve_input_root(DATASET_ID)
if root is None or file_count == 0:
    write_failfast("missing_input_dir_or_empty", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)

raw_path = find_file(files, "sample_audvis_raw.fif")
if raw_path is None:
    write_failfast("missing_raw_fif", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)

try:
    raw = mne.io.read_raw_fif(raw_path, preload=True, verbose="ERROR")
    raw.crop(0.0, min(30.0, raw.times[-1]))
    raw.pick(["meg", "eog"], exclude=[])
    raw.filter(1.0, 40.0, verbose="ERROR")

    n_meg = len(mne.pick_types(raw.info, meg=True, eeg=False, eog=False))
    n_components = max(5, min(20, n_meg - 1))
    ica = mne.preprocessing.ICA(n_components=n_components, random_state=97, max_iter="auto", method="fastica")
    ica.fit(raw.copy().pick("meg"), decim=5, reject_by_annotation=True, verbose="ERROR")

    eog_picks = mne.pick_types(raw.info, meg=False, eeg=False, eog=True)
    eog_name = raw.ch_names[eog_picks[0]] if len(eog_picks) > 0 else ""
    eog_inds = []
    eog_scores = []
    if eog_name:
        try:
            eog_inds, eog_scores = ica.find_bads_eog(raw, ch_name=eog_name, verbose="ERROR")
        except Exception:
            eog_inds, eog_scores = [], []
    ica.exclude = list(eog_inds[:3])

    ica.save(output_dir / "ica_solution.fif", overwrite=True)

    fig = ica.plot_components(picks=list(range(min(10, ica.n_components_))), show=False)
    if isinstance(fig, list):
        fig = fig[0]
    fig.savefig(output_dir / "component_topographies.png", dpi=120)
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
            "n_channels": int(len(raw.ch_names)),
            "n_components": int(ica.n_components_),
            "n_excluded": int(len(ica.exclude)),
            "excluded_components": [int(i) for i in ica.exclude],
            "eog_channel": eog_name,
            "max_abs_eog_score": float(np.max(np.abs(eog_scores))) if len(eog_scores) else 0.0,
        },
    )
except Exception as exc:
    write_failfast(f"compute_error: {exc.__class__.__name__}", root, checked_paths, file_count, byte_count)
