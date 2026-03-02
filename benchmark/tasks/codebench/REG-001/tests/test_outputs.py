import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED = ["registered_T1w.nii.gz", "composite_warp.nii.gz", "run_metadata.json"]


def _load(name: str) -> np.ndarray:
    arr = np.asarray(nib.load(str(OUTPUT_DIR / name)).get_fdata(), dtype=float)
    return arr


def test_required_outputs_exist():
    for name in REQUIRED:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected a file: {p}"


def test_registration_outputs_semantic_validity():
    reg = _load("registered_T1w.nii.gz")
    warp = _load("composite_warp.nii.gz")

    assert reg.ndim == 3
    assert warp.ndim == 3
    assert reg.shape == warp.shape
    assert reg.size > 0

    assert np.isfinite(reg).all(), "registered_T1w contains non-finite values"
    assert np.isfinite(warp).all(), "composite_warp contains non-finite values"

    assert float(np.std(reg)) > 1e-6, "registered_T1w appears constant"
    assert float(np.min(warp)) >= -1e-6, "composite_warp should be non-negative"
    assert float(np.mean(warp)) > 0.0, "composite_warp mean should be positive"
    assert float(np.std(warp)) > 1e-6, "composite_warp appears constant"


def test_run_metadata_consistency():
    reg = _load("registered_T1w.nii.gz")
    warp = _load("composite_warp.nii.gz")
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))

    assert meta.get("task_id") == "REG-001"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds000105"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"

    assert str(meta.get("snapshot_tag", "")).strip()
    assert str(meta.get("subject_id", "")).startswith("sub-")

    assert meta.get("registered_shape") == list(reg.shape)
    assert meta.get("template_shape") == list(reg.shape)

    assert abs(float(meta.get("warp_mean", -1.0)) - float(np.mean(warp))) <= 1e-5
    assert abs(float(meta.get("registered_mean", -1.0)) - float(np.mean(reg))) <= 1e-5

    assert int(meta.get("records_count", -1)) == 2
    assert int(meta.get("bytes_total", -1)) > 0
