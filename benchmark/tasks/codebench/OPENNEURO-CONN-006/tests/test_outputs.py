import csv
import hashlib
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
N_COMPONENTS = 20


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames is not None
        rows = list(reader)
    return reader.fieldnames, rows


def test_required_outputs_exist():
    for name in [
        "ica_components.nii.gz",
        "stats.csv",
        "component_timeseries.csv",
        "input_manifest.csv",
        "run_metadata.json",
    ]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_ica_nifti_validity():
    img = nib.load(str(OUTPUT_DIR / "ica_components.nii.gz"))
    arr = np.asarray(img.get_fdata(), dtype=float)

    assert arr.ndim == 4
    assert arr.shape[3] == N_COMPONENTS
    assert np.isfinite(arr).all()
    assert float(np.std(arr)) > 1e-6


def test_stats_and_component_timeseries_schema():
    s_fields, s_rows = _read_csv(OUTPUT_DIR / "stats.csv")
    for col in [
        "component_id",
        "group_diff_t",
        "stability_corr",
        "component_mean",
        "component_std",
        "n_subjects",
        "n_paired_subjects",
        "snapshot_tag",
        "method",
    ]:
        assert col in s_fields

    assert len(s_rows) == N_COMPONENTS
    comp_ids = sorted(int(r["component_id"]) for r in s_rows)
    assert comp_ids == list(range(1, N_COMPONENTS + 1))

    for r in s_rows:
        assert np.isfinite(float(r["group_diff_t"]))
        assert -1.0 <= float(r["stability_corr"]) <= 1.0
        assert np.isfinite(float(r["component_mean"]))
        assert float(r["component_std"]) >= 0.0
        assert int(r["n_subjects"]) >= 1
        assert int(r["n_paired_subjects"]) >= 0
        assert r["method"] == "voxelwise_msdl_fastica"

    t_fields, t_rows = _read_csv(OUTPUT_DIR / "component_timeseries.csv")
    for col in [
        "subject_id",
        "session",
        "run_id",
        "component_id",
        "mean_abs_source",
        "std_source",
        "n_timepoints",
    ]:
        assert col in t_fields

    assert t_rows
    seen_components = set()
    for r in t_rows:
        cid = int(r["component_id"])
        assert 1 <= cid <= N_COMPONENTS
        seen_components.add(cid)
        assert r["subject_id"].startswith("sub-")
        assert int(r["n_timepoints"]) >= 20
        assert float(r["mean_abs_source"]) >= 0.0
        assert float(r["std_source"]) >= 0.0

    assert seen_components == set(range(1, N_COMPONENTS + 1))


def test_run_metadata_traceability():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))

    assert meta.get("task_id") == "OPENNEURO-CONN-006"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds001168"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"
    assert str(meta.get("snapshot_tag", "")).strip()

    assert int(meta.get("n_components", -1)) == N_COMPONENTS
    assert meta.get("map_shape") is not None
    assert int(meta.get("processing_subject_count", -1)) >= 1
    assert int(meta.get("processing_run_count", -1)) >= 1
    assert int(meta.get("input_file_count", -1)) >= int(meta.get("processing_run_count", -1))

    assert int(meta.get("records_count", -1)) == 4
    assert int(meta.get("bytes_total", -1)) > 0

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha
