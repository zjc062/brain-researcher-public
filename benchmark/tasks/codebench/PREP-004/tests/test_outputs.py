import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))


def test_required_outputs_exist():
    for name in ["motion_corrected_bold.nii.gz", "motion_parameters.txt", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_motion_corrected_outputs_semantics():
    img = nib.load(str(OUTPUT_DIR / "motion_corrected_bold.nii.gz"))
    arr = np.asarray(img.get_fdata(), dtype=float)

    assert arr.ndim == 4
    assert arr.shape[3] >= 10
    assert np.isfinite(arr).all()
    assert float(np.std(arr)) > 1e-6

    params = np.loadtxt(OUTPUT_DIR / "motion_parameters.txt")
    if params.ndim == 1:
        params = params.reshape(1, -1)
    assert params.shape == (arr.shape[3], 6)
    assert np.isfinite(params).all()
    assert float(np.max(np.abs(params[:, :3]))) > 0.0, "Translations should not be all zero"


def test_run_metadata_consistency():
    arr = np.asarray(nib.load(str(OUTPUT_DIR / "motion_corrected_bold.nii.gz")).get_fdata(), dtype=float)
    params = np.loadtxt(OUTPUT_DIR / "motion_parameters.txt")
    if params.ndim == 1:
        params = params.reshape(1, -1)

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta.get("task_id") == "PREP-004"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds003592"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"

    assert str(meta.get("snapshot_tag", "")).strip()
    assert str(meta.get("subject_id", "")).startswith("sub-")

    assert meta.get("shape") == list(arr.shape)
    assert int(meta.get("n_timepoints", -1)) == arr.shape[3]
    mean_abs = float(np.mean(np.abs(params[:, :3])))
    assert abs(float(meta.get("mean_abs_translation", -1.0)) - mean_abs) <= 1e-5

    assert int(meta.get("records_count", -1)) == 2
    assert int(meta.get("bytes_total", -1)) > 0
