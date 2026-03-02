import csv
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["vlsm_map.nii.gz", "deficit_correlations.csv"]
OUTPUT_SCHEMA = {
    "vlsm_map.nii.gz": {"type": "nifti", "no_nan": True},
    "deficit_correlations.csv": {
        "type": "csv",
        "required_columns": [
            "voxel_index",
            "x",
            "y",
            "z",
            "correlation_r",
            "t_stat",
            "p_value",
            "n_subjects",
            "status",
            "reason",
        ],
    },
}
METRIC_VALIDATION = {}


def _read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None, f"CSV header missing: {path}"
        rows = list(reader)
    return reader.fieldnames, rows


def _to_int(value):
    return int(float(str(value).strip()))


def _to_float(value):
    return float(str(value).strip())


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Required output is not a file: {p}"


def test_csv_schema_and_basic_ranges():
    fieldnames, rows = _read_csv(OUTPUT_DIR / "deficit_correlations.csv")
    for col in OUTPUT_SCHEMA["deficit_correlations.csv"]["required_columns"]:
        assert col in fieldnames, f"Missing required column: {col}"
    assert rows, "deficit_correlations.csv must not be empty"

    for row in rows:
        status = row["status"].strip().lower()
        reason = row["reason"].strip()
        assert status in {"ok", "failed_precondition"}
        assert reason, "reason must be non-empty"

        r = _to_float(row["correlation_r"])
        p = _to_float(row["p_value"])
        n = _to_int(row["n_subjects"])
        assert -1.0 <= r <= 1.0
        assert 0.0 <= p <= 1.0
        assert n >= 0


def test_nifti_loads_and_matches_mode():
    img = nib.load(str(OUTPUT_DIR / "vlsm_map.nii.gz"))
    arr = np.asarray(img.get_fdata(), dtype=float)
    assert arr.ndim == 3
    assert np.all(np.isfinite(arr))

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()

    if status == "ok":
        assert np.std(arr) > 0.0, "vlsm_map should contain non-constant statistics in ok mode"
    else:
        assert status == "failed_precondition"


def test_cross_file_consistency_with_run_metadata():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta.get("task_id") == "CLIN-006"
    assert meta.get("dataset_source") == "Provided"
    assert meta.get("dataset_id") == "simulated_lesion_symptom_data"

    _, rows = _read_csv(OUTPUT_DIR / "deficit_correlations.csv")
    csv_statuses = {r["status"].strip().lower() for r in rows}
    csv_reasons = {r["reason"].strip() for r in rows}

    run_status = str(meta.get("status", "")).strip().lower()
    run_reason = str(meta.get("reason", "")).strip()
    assert run_status in {"ok", "failed_precondition"}
    assert csv_statuses == {run_status}
    assert run_reason
    assert csv_reasons == {run_reason}

    if run_status == "ok":
        assert int(meta.get("n_subjects_used")) >= 4
        assert int(meta.get("n_voxels_tested")) >= 10
        assert int(meta.get("n_rows_reported")) == len(rows)

        img = nib.load(str(OUTPUT_DIR / "vlsm_map.nii.gz"))
        arr = np.asarray(img.get_fdata(), dtype=float)
        for row in rows[:20]:
            x = _to_int(row["x"])
            y = _to_int(row["y"])
            z = _to_int(row["z"])
            rv = _to_float(row["correlation_r"])
            assert abs(float(arr[x, y, z]) - rv) <= 1e-5
    else:
        assert int(meta.get("n_subjects_used")) == 0
        assert int(meta.get("n_rows_reported")) >= 1
        assert str(meta.get("reason", "")).strip()
