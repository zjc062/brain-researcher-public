import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))


def test_required_outputs_exist():
    for name in ["combined_bold.nii.gz", "t2star_map.nii.gz", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_multi_echo_outputs_semantics():
    comb = np.asarray(nib.load(str(OUTPUT_DIR / "combined_bold.nii.gz")).get_fdata(), dtype=float)
    t2 = np.asarray(nib.load(str(OUTPUT_DIR / "t2star_map.nii.gz")).get_fdata(), dtype=float)

    assert comb.ndim == 4
    assert comb.shape[3] >= 5
    assert t2.ndim == 3
    assert list(comb.shape[:3]) == list(t2.shape)

    assert np.isfinite(comb).all()
    assert np.isfinite(t2).all()
    assert float(np.std(comb)) > 1e-6
    assert float(np.std(t2)) > 1e-6

    assert float(np.min(t2)) >= -1e-8
    assert float(np.max(t2)) <= 0.2000001


def test_run_metadata_consistency():
    comb = np.asarray(nib.load(str(OUTPUT_DIR / "combined_bold.nii.gz")).get_fdata(), dtype=float)
    t2 = np.asarray(nib.load(str(OUTPUT_DIR / "t2star_map.nii.gz")).get_fdata(), dtype=float)
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))

    assert meta.get("task_id") == "PREP-010"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds000216"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"

    assert str(meta.get("snapshot_tag", "")).strip()
    assert str(meta.get("subject_id", "")).startswith("sub-")

    assert int(meta.get("echo_count", 0)) >= 2
    echo_indices = meta.get("echo_indices", [])
    assert isinstance(echo_indices, list) and len(echo_indices) == int(meta.get("echo_count", -1))

    assert meta.get("shape") == list(comb.shape)
    assert abs(float(meta.get("t2star_mean", -1.0)) - float(np.mean(t2))) <= 1e-5

    assert int(meta.get("records_count", -1)) == 2
    assert int(meta.get("bytes_total", -1)) > 0
