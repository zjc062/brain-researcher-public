import csv
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["corrected_dwi.nii.gz", "eddy_movement.txt"]
OUTPUT_SCHEMA = {
    "corrected_dwi.nii.gz": {"type": "nifti", "no_nan": True},
    "eddy_movement.txt": {"type": "text"},
}
METRIC_VALIDATION = {}


def _read_rows(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None, f"Missing header: {path}"
        rows = list(reader)
    return reader.fieldnames, rows


def _as_float(value):
    return float(str(value).strip())


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Required output is not a file: {p}"



def test_run_metadata_contract():
    meta_path = OUTPUT_DIR / "run_metadata.json"
    assert meta_path.exists(), "run_metadata.json is required"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta.get("task_id") == "DIFF-001"
    assert meta.get("dataset_source") == "Provided"
    assert meta.get("dataset_id") == "custom_dwi_bids"

    status = str(meta.get("status", "")).strip().lower()
    reason = str(meta.get("reason", "")).strip()
    assert status in {"ok", "failed_precondition"}
    assert reason
    assert int(meta.get("records_count", 0)) >= 0
    assert int(meta.get("bytes_total", 0)) >= 0



def test_motion_file_schema():
    fieldnames, rows = _read_rows(OUTPUT_DIR / "eddy_movement.txt")
    expected = ["volume", "bval", "shift_x", "shift_y", "shift_z", "scale"]
    assert fieldnames == expected
    assert len(rows) >= 1

    for row in rows:
        _as_float(row["bval"])
        for key in ["shift_x", "shift_y", "shift_z", "scale"]:
            value = _as_float(row[key])
            assert np.isfinite(value), f"Non-finite value in {key}"



def test_corrected_dwi_semantics_and_cross_file_consistency():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()

    img = nib.load(str(OUTPUT_DIR / "corrected_dwi.nii.gz"))
    data = np.asarray(img.dataobj)

    assert data.ndim == 4, "corrected_dwi.nii.gz must be 4D"
    assert data.shape[3] >= 1
    assert np.all(np.isfinite(data)), "corrected DWI contains non-finite values"

    _, rows = _read_rows(OUTPUT_DIR / "eddy_movement.txt")
    assert len(rows) == int(data.shape[3]), "motion row count must equal number of volumes"

    if status == "ok":
        assert int(meta.get("n_volumes", 0)) == int(data.shape[3])
        assert float(meta.get("mean_abs_shift_vox", 0.0)) >= 0.0
        assert int(meta.get("mask_voxels", 0)) > 0

        input_path = Path(str(meta.get("input_dwi_path", "")))
        assert input_path.exists(), "input_dwi_path in run_metadata must exist"

        sample = data[..., 0]
        assert float(np.mean(np.abs(sample))) > 0.0, "corrected data appears empty"
    else:
        assert status == "failed_precondition"

