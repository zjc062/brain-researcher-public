import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED = ["flirt_matrix.mat", "coregistered_bold.nii.gz", "run_metadata.json"]


def _load_matrix() -> np.ndarray:
    mat = np.loadtxt(OUTPUT_DIR / "flirt_matrix.mat")
    if mat.ndim == 1:
        mat = mat.reshape(4, 4)
    return mat


def _load_coreg() -> np.ndarray:
    return np.asarray(nib.load(str(OUTPUT_DIR / "coregistered_bold.nii.gz")).get_fdata(), dtype=float)


def test_required_outputs_exist():
    for name in REQUIRED:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected a file: {p}"


def test_matrix_and_coregistered_bold_validity():
    mat = _load_matrix()
    arr = _load_coreg()

    assert mat.shape == (4, 4)
    assert np.isfinite(mat).all(), "flirt_matrix has non-finite values"
    assert float(np.linalg.norm(mat - np.eye(4))) > 1e-4, "flirt_matrix should not be identity"
    assert abs(float(np.linalg.det(mat))) > 1e-8, "flirt_matrix must be invertible"

    assert arr.ndim == 3
    assert arr.size > 0
    assert np.isfinite(arr).all(), "coregistered_bold contains non-finite values"
    assert float(np.std(arr)) > 1e-6, "coregistered_bold appears constant"


def test_run_metadata_consistency():
    mat = _load_matrix()
    arr = _load_coreg()
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))

    assert meta.get("task_id") == "REG-002"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds002424"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"

    assert str(meta.get("snapshot_tag", "")).strip()
    assert str(meta.get("subject_id", "")).startswith("sub-")
    assert int(meta.get("bold_timepoints", 0)) >= 1

    assert meta.get("coregistered_shape") == list(arr.shape)
    assert abs(float(meta.get("matrix_det", 0.0)) - float(np.linalg.det(mat))) <= 1e-6

    assert int(meta.get("records_count", -1)) == 2
    assert int(meta.get("bytes_total", -1)) > 0
