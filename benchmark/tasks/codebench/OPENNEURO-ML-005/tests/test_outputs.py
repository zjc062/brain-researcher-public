import csv
import hashlib
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))


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
    for name in ["searchlight_map.nii.gz", "results.json", "input_manifest.csv", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_searchlight_map_validity():
    arr = np.asarray(nib.load(str(OUTPUT_DIR / "searchlight_map.nii.gz")).get_fdata(), dtype=float)
    assert arr.ndim == 3
    assert np.isfinite(arr).all()
    assert float(np.min(arr)) >= 0.0
    assert float(np.max(arr)) <= 1.0 + 1e-6
    assert float(np.std(arr)) > 0.0


def test_results_and_manifest_consistency():
    results = json.loads((OUTPUT_DIR / "results.json").read_text(encoding="utf-8"))
    for key in [
        "dataset_id",
        "snapshot_tag",
        "subject_id",
        "run",
        "chance_level",
        "mean_accuracy",
        "n_trials",
        "n_categories",
        "status",
        "reason",
        "method",
    ]:
        assert key in results

    assert results["dataset_id"] == "ds000105"
    assert str(results["snapshot_tag"]).strip()
    assert str(results["subject_id"]).startswith("sub-")
    assert str(results["run"]).strip()
    assert results["status"] == "ok"
    assert results["reason"] == "computed"
    assert results["method"] == "real_bold_events_decoding_proxy"

    chance = float(results["chance_level"])
    mean_acc = float(results["mean_accuracy"])
    assert 0.0 < chance < 1.0
    assert int(results["n_categories"]) == 8
    assert int(results["n_trials"]) >= 16
    assert chance <= mean_acc <= 1.0

    map_arr = np.asarray(nib.load(str(OUTPUT_DIR / "searchlight_map.nii.gz")).get_fdata(), dtype=float)
    mask = map_arr > chance + 1e-8
    if np.any(mask):
        map_mean = float(np.mean(map_arr[mask]))
    else:
        map_mean = float(np.mean(map_arr))
    assert abs(map_mean - mean_acc) <= 1e-3

    m_fields, m_rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
    for col in [
        "dataset_id",
        "snapshot_tag",
        "subject_id",
        "run",
        "bold_relpath",
        "events_relpath",
        "bold_local_path",
        "events_local_path",
        "bold_bytes",
        "events_bytes",
        "bold_sha256",
        "events_sha256",
    ]:
        assert col in m_fields

    assert len(m_rows) == 1
    row = m_rows[0]
    assert row["dataset_id"] == "ds000105"
    assert row["snapshot_tag"] == results["snapshot_tag"]
    assert row["subject_id"] == results["subject_id"]
    assert row["run"] == results["run"]
    assert int(row["bold_bytes"]) > 0
    assert int(row["events_bytes"]) > 0
    for hkey in ["bold_sha256", "events_sha256"]:
        s = row[hkey].strip().lower()
        assert len(s) == 64
        int(s, 16)


def test_run_metadata_consistency():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    results = json.loads((OUTPUT_DIR / "results.json").read_text(encoding="utf-8"))

    assert meta.get("task_id") == "OPENNEURO-ML-005"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds000105"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"

    assert meta.get("snapshot_tag") == results.get("snapshot_tag")
    assert meta.get("subject_id") == results.get("subject_id")
    assert meta.get("run") == results.get("run")
    assert meta.get("method") == results.get("method")

    assert int(meta.get("processing_subject_count", -1)) == 1
    assert int(meta.get("processing_run_count", -1)) == 1
    assert int(meta.get("input_file_count", -1)) == 2
    assert int(meta.get("input_bytes_total", -1)) > 0
    assert int(meta.get("records_count", -1)) == 3
    assert int(meta.get("bytes_total", -1)) > 0

    assert abs(float(meta.get("chance_level")) - float(results.get("chance_level"))) <= 1e-9
    assert abs(float(meta.get("mean_accuracy")) - float(results.get("mean_accuracy"))) <= 1e-9
    assert int(meta.get("n_trials")) == int(results.get("n_trials"))

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha
