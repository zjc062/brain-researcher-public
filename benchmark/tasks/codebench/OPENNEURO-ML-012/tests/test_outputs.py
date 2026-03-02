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
    for name in ["age_preds.csv", "uncertainty.nii.gz", "input_manifest.csv", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_uncertainty_map_validity():
    arr = np.asarray(nib.load(str(OUTPUT_DIR / "uncertainty.nii.gz")).get_fdata(), dtype=float)
    assert arr.ndim == 3
    assert np.isfinite(arr).all()
    assert float(np.min(arr)) >= 0.0
    assert float(np.max(arr)) <= 1.0 + 1e-6
    assert float(np.std(arr)) > 1e-8


def test_predictions_schema_and_status_contract():
    fields, rows = _read_csv(OUTPUT_DIR / "age_preds.csv")
    for col in [
        "subject_id",
        "actual_age",
        "predicted_age",
        "std_dev",
        "status",
        "reason",
        "dataset_id",
        "snapshot_tag",
        "method",
    ]:
        assert col in fields

    assert rows
    statuses = {r["status"] for r in rows}
    assert len(statuses) == 1
    status = rows[0]["status"]
    reason = rows[0]["reason"]

    for r in rows:
        assert r["subject_id"].startswith("sub-")
        assert float(r["actual_age"]) > 0.0
        assert r["dataset_id"] == "ds000030"
        assert str(r["snapshot_tag"]).strip()
        assert r["method"] == "real_bold_gpr_age_prediction"
        assert r["status"] == status
        assert r["reason"] == reason

    if status == "ok":
        assert len(rows) >= 2
        for r in rows:
            p = float(r["predicted_age"])
            s = float(r["std_dev"])
            assert np.isfinite(p)
            assert np.isfinite(s)
            assert s >= 0.0
    else:
        assert status == "failed_precondition"
        assert "subjects<2" in reason
        for r in rows:
            assert r["predicted_age"] == "NA"
            assert r["std_dev"] == "NA"


def test_manifest_and_run_metadata_consistency():
    m_fields, m_rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
    for col in ["dataset_id", "snapshot_tag", "subject_id", "run", "remote_relpath", "local_path", "bytes", "sha256"]:
        assert col in m_fields

    assert m_rows
    for r in m_rows:
        assert r["dataset_id"] == "ds000030"
        assert r["subject_id"].startswith("sub-")
        assert str(r["run"]).strip()
        assert int(r["bytes"]) > 0
        s = r["sha256"].strip().lower()
        assert len(s) == 64
        int(s, 16)

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta.get("task_id") == "OPENNEURO-ML-012"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds000030"
    assert meta.get("status") in {"ok", "failed_precondition"}
    assert str(meta.get("reason", "")).strip()
    assert str(meta.get("snapshot_tag", "")).strip()
    assert meta.get("method") == "real_bold_gpr_age_prediction"

    assert int(meta.get("processing_subject_count", -1)) >= 1
    assert int(meta.get("processing_run_count", -1)) >= 1
    assert int(meta.get("input_file_count", -1)) == len(m_rows)
    assert int(meta.get("input_bytes_total", -1)) == sum(int(r["bytes"]) for r in m_rows)
    assert int(meta.get("records_count", -1)) == 3
    assert int(meta.get("bytes_total", -1)) > 0

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha

    _, rows = _read_csv(OUTPUT_DIR / "age_preds.csv")
    assert meta.get("status") == rows[0]["status"]
    assert meta.get("reason") == rows[0]["reason"]
    assert meta.get("snapshot_tag") == rows[0]["snapshot_tag"]
