import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED = ["native_space_results.nii.gz", "inverse_warp.nii.gz", "run_metadata.json"]


def _load(name: str) -> np.ndarray:
    return np.asarray(nib.load(str(OUTPUT_DIR / name)).get_fdata(), dtype=float)


def test_required_outputs_exist():
    for name in REQUIRED:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected a file: {p}"


def test_inverse_normalization_outputs_validity():
    native = _load("native_space_results.nii.gz")
    warp = _load("inverse_warp.nii.gz")

    assert native.ndim == 3
    assert warp.ndim == 3
    assert native.shape == warp.shape
    assert native.size > 0

    assert np.isfinite(native).all(), "native_space_results contains non-finite values"
    assert np.isfinite(warp).all(), "inverse_warp contains non-finite values"

    assert float(np.std(native)) > 1e-6, "native_space_results appears constant"
    assert float(np.min(warp)) >= -1e-6, "inverse_warp should be non-negative"
    assert float(np.mean(warp)) > 0.0, "inverse_warp mean should be positive"
    assert float(np.max(warp)) > float(np.mean(warp)), "inverse_warp should have dynamic range"


def test_run_metadata_consistency():
    native = _load("native_space_results.nii.gz")
    warp = _load("inverse_warp.nii.gz")
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))

    assert meta.get("task_id") == "REG-010"
    assert meta.get("dataset_source") == "Nilearn"
    assert meta.get("dataset_id") == "fetch_miyawaki2008"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"

    assert meta.get("native_results_shape") == list(native.shape)
    assert meta.get("inverse_warp_shape") == list(warp.shape)

    assert abs(float(meta.get("native_results_mean", -1.0)) - float(np.mean(native))) <= 1e-5
    assert abs(float(meta.get("warp_mean", -1.0)) - float(np.mean(warp))) <= 1e-5
    assert abs(float(meta.get("warp_max", -1.0)) - float(np.max(warp))) <= 1e-5

    assert int(meta.get("records_count", -1)) == 2
    assert int(meta.get("bytes_total", -1)) > 0
