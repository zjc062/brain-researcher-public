import csv
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))


def _read_components():
    with (OUTPUT_DIR / "compcor_components.tsv").open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        assert reader.fieldnames is not None
        assert "timepoint" in reader.fieldnames
        comp_cols = [c for c in reader.fieldnames if c.startswith("compcor_")]
        assert len(comp_cols) >= 3
        rows = list(reader)
    return comp_cols, rows


def test_required_outputs_exist():
    for name in ["cleaned_bold.nii.gz", "compcor_components.tsv", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_cleaned_bold_and_compcor_table_semantics():
    arr = np.asarray(nib.load(str(OUTPUT_DIR / "cleaned_bold.nii.gz")).get_fdata(), dtype=float)
    assert arr.ndim == 4
    assert arr.shape[3] >= 20
    assert np.isfinite(arr).all()
    assert float(np.std(arr)) > 1e-6

    comp_cols, rows = _read_components()
    assert len(rows) == arr.shape[3]

    mat = np.zeros((len(rows), len(comp_cols)), dtype=float)
    for i, r in enumerate(rows):
        assert int(r["timepoint"]) == i
        for j, c in enumerate(comp_cols):
            mat[i, j] = float(r[c])

    assert np.isfinite(mat).all()
    assert np.all(np.std(mat, axis=0) > 1e-8), "Each CompCor component should vary over time"


def test_run_metadata_consistency():
    arr = np.asarray(nib.load(str(OUTPUT_DIR / "cleaned_bold.nii.gz")).get_fdata(), dtype=float)
    comp_cols, _ = _read_components()
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))

    assert meta.get("task_id") == "PREP-012"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds000105"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"

    assert str(meta.get("snapshot_tag", "")).strip()
    assert str(meta.get("subject_id", "")).startswith("sub-")

    assert meta.get("shape") == list(arr.shape)
    assert int(meta.get("n_components", -1)) == len(comp_cols)
    assert int(meta.get("noise_voxels", 0)) >= 200

    ev = meta.get("explained_variance_ratio", [])
    assert isinstance(ev, list) and len(ev) == len(comp_cols)
    assert all(float(v) >= 0.0 for v in ev)

    assert int(meta.get("records_count", -1)) == 2
    assert int(meta.get("bytes_total", -1)) > 0
