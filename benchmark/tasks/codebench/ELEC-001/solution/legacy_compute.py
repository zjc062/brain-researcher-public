import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mne
import numpy as np

TASK_ID = "ELEC-001"
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
    info = mne.create_info(["MEG0111", "MEG0112", "EOG061"], sfreq=600.0, ch_types=["grad", "grad", "eog"])
    data = np.zeros((3, 1200), dtype=float)
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    raw.save(output_dir / "clean_raw.fif", overwrite=True)

    report = f"""<html><body><h1>ELEC-001 fail-fast</h1><p>Status: failed_precondition</p><p>Reason: {reason}</p></body></html>"""
    (output_dir / "preprocessing_report.html").write_text(report, encoding="utf-8")

    write_run_metadata("failed_precondition", reason, data_root, checked_paths, records_count, bytes_total, extras={"method": "maxwell+filter"})


root, checked_paths, files, file_count, byte_count = resolve_input_root(DATASET_ID)
if root is None or file_count == 0:
    write_failfast("missing_input_dir_or_empty", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)

raw_path = find_file(files, "sample_audvis_raw.fif")
cal_path = find_file(files, "sss_cal_mgh.dat")
ct_path = find_file(files, "ct_sparse_mgh.fif")

if raw_path is None:
    write_failfast("missing_raw_fif", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)
if cal_path is None or ct_path is None:
    write_failfast("missing_sss_calibration_or_crosstalk", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)

try:
    raw = mne.io.read_raw_fif(raw_path, preload=True, verbose="ERROR")
    raw.crop(0.0, min(20.0, raw.times[-1]))
    raw.pick(["meg"], exclude=[])

    cleaned = mne.preprocessing.maxwell_filter(
        raw,
        calibration=str(cal_path),
        cross_talk=str(ct_path),
        st_duration=None,
        verbose="ERROR",
    )
    cleaned.filter(1.0, 40.0, verbose="ERROR")
    cleaned.notch_filter([60.0], verbose="ERROR")
    cleaned.save(output_dir / "clean_raw.fif", overwrite=True)

    report = f"""
<html>
  <body>
    <h1>ELEC-001 Preprocessing Report</h1>
    <p>Status: ok</p>
    <ul>
      <li>Raw file: {raw_path}</li>
      <li>Calibration: {cal_path}</li>
      <li>Cross-talk: {ct_path}</li>
      <li>Method: Maxwell filtering + 1-40 Hz band-pass + 60 Hz notch</li>
      <li>Channels: {len(cleaned.ch_names)}</li>
      <li>Duration (s): {cleaned.times[-1]:.3f}</li>
    </ul>
  </body>
</html>
""".strip()
    (output_dir / "preprocessing_report.html").write_text(report, encoding="utf-8")

    write_run_metadata(
        "ok",
        "computed",
        root,
        checked_paths,
        file_count,
        byte_count,
        extras={
            "raw_path": str(raw_path),
            "calibration_path": str(cal_path),
            "crosstalk_path": str(ct_path),
            "n_channels_clean": int(len(cleaned.ch_names)),
            "duration_sec": float(cleaned.times[-1]),
            "sfreq": float(cleaned.info["sfreq"]),
        },
    )
except Exception as exc:
    write_failfast(f"compute_error: {exc.__class__.__name__}", root, checked_paths, file_count, byte_count)
