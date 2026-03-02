import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))


def load_metadata() -> dict:
    return json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))


def test_required_outputs_exist():
    for name in ["filtered_bold.nii.gz", "power_spectrum.png", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_filtered_bold_and_png_validity():
    meta = load_metadata()
    status = str(meta.get("status", "")).strip()
    assert status in {"ok", "failed_precondition"}

    arr = np.asarray(nib.load(str(OUTPUT_DIR / "filtered_bold.nii.gz")).get_fdata(), dtype=float)
    assert np.isfinite(arr).all()
    if status == "ok":
        assert arr.ndim == 4
        assert arr.shape[3] >= 20
        assert float(np.std(arr)) > 1e-6
    else:
        assert arr.ndim in {3, 4}
        assert arr.size > 0

    png = (OUTPUT_DIR / "power_spectrum.png").read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 512


def test_run_metadata_consistency():
    arr = np.asarray(nib.load(str(OUTPUT_DIR / "filtered_bold.nii.gz")).get_fdata(), dtype=float)
    meta = load_metadata()

    assert meta.get("task_id") == "PREP-009"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds000030"

    status = str(meta.get("status", "")).strip()
    assert status in {"ok", "failed_precondition"}
    assert str(meta.get("reason", "")).strip()

    if status == "ok":
        assert str(meta.get("snapshot_tag", "")).strip()
        assert str(meta.get("subject_id", "")).startswith("sub-")
        assert meta.get("shape") == list(arr.shape)
        assert float(meta.get("tr", 0.0)) > 0.0
        assert abs(float(meta.get("low_hz", -1.0)) - 0.01) <= 1e-9
        assert abs(float(meta.get("high_hz", -1.0)) - 0.10) <= 1e-9

        pre = float(meta.get("pre_highfreq_ratio", 2.0))
        post = float(meta.get("post_highfreq_ratio", 2.0))
        assert 0.0 <= pre <= 1.0 + 1e-6
        assert 0.0 <= post <= 1.0 + 1e-6
        assert post < pre, "Band-pass output should reduce >0.1Hz ratio"

    assert int(meta.get("records_count", 0)) >= 0
