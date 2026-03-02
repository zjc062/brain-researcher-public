import csv
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))


def _find_denoised_files():
    return sorted(OUTPUT_DIR.glob("*_desc-smoothAROMAnonaggr_bold.nii.gz"))


def _read_mixing_rows():
    with (OUTPUT_DIR / "mixing_matrix.tsv").open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        assert reader.fieldnames is not None
        for c in ["component_id", "variance_explained", "hf_ratio", "motion_corr", "is_motion", "n_timepoints"]:
            assert c in reader.fieldnames
        return list(reader)


def test_required_outputs_exist():
    files = _find_denoised_files()
    assert files, "Missing required output matching *_desc-smoothAROMAnonaggr_bold.nii.gz"
    assert (OUTPUT_DIR / "mixing_matrix.tsv").exists()
    assert (OUTPUT_DIR / "run_metadata.json").exists()


def test_denoised_bold_and_mixing_semantics():
    files = _find_denoised_files()
    arr = np.asarray(nib.load(str(files[0])).get_fdata(), dtype=float)

    assert arr.ndim == 4
    assert arr.shape[3] >= 20
    assert np.isfinite(arr).all()
    assert float(np.std(arr)) > 1e-6

    rows = _read_mixing_rows()
    assert len(rows) >= 3

    flags = []
    for r in rows:
        cid = int(r["component_id"])
        assert cid >= 1
        vexp = float(r["variance_explained"])
        hf = float(r["hf_ratio"])
        corr = float(r["motion_corr"])
        is_motion = int(r["is_motion"])
        n_tp = int(r["n_timepoints"])

        assert 0.0 <= vexp <= 1.0
        assert 0.0 <= hf <= 1.0 + 1e-6
        assert 0.0 <= corr <= 1.0 + 1e-6
        assert is_motion in (0, 1)
        assert n_tp == arr.shape[3]
        flags.append(is_motion)

    assert sum(flags) >= 1, "At least one motion component should be identified"


def test_run_metadata_consistency():
    files = _find_denoised_files()
    arr = np.asarray(nib.load(str(files[0])).get_fdata(), dtype=float)
    rows = _read_mixing_rows()
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))

    assert meta.get("task_id") == "PREP-002"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds002424"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"

    assert str(meta.get("snapshot_tag", "")).strip()
    assert str(meta.get("subject_id", "")).startswith("sub-")
    assert str(meta.get("output_bold_file", "")) == files[0].name

    assert meta.get("shape") == list(arr.shape)
    assert int(meta.get("n_components", -1)) == len(rows)
    assert int(meta.get("n_motion_components", -1)) >= 1

    assert int(meta.get("records_count", -1)) == 2
    assert int(meta.get("bytes_total", -1)) > 0
