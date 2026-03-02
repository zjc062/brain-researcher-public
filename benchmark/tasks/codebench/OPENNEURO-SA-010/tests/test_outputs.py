import csv
import hashlib
import json
import os
from pathlib import Path

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
    for name in ["age_model_results.csv", "input_manifest.csv", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_age_model_schema_and_status_contract():
    fields, rows = _read_csv(OUTPUT_DIR / "age_model_results.csv")
    for col in [
        "connection",
        "age_squared_p",
        "beta_age",
        "beta_age2",
        "status",
        "reason",
        "subjects_included",
        "sites_included",
        "age_min",
        "age_max",
        "age_span",
        "runs_used",
        "dataset_id",
        "snapshot_tag",
        "method",
    ]:
        assert col in fields

    assert len(rows) == 1
    row = rows[0]

    assert row["connection"] == "GLOBAL_DMN_MEAN_ABS_FC"
    assert row["dataset_id"] == "ds000030"
    assert row["method"] == "real_bold_quadratic_age_model"
    assert row["status"] in {"ok", "failed_precondition"}
    assert row["reason"].strip()
    assert int(row["subjects_included"]) >= 0
    assert int(row["sites_included"]) >= 1
    assert int(row["runs_used"]) >= 0
    assert float(row["age_span"]) >= 0.0

    if row["status"] == "ok":
        p = float(row["age_squared_p"])
        b1 = float(row["beta_age"])
        b2 = float(row["beta_age2"])
        assert 0.0 <= p <= 1.0
        assert abs(b1) < 1e6
        assert abs(b2) < 1e6
        assert int(row["subjects_included"]) >= 8
    else:
        assert row["age_squared_p"] == "NA"
        assert row["beta_age"] == "NA"
        assert row["beta_age2"] == "NA"
        reason = row["reason"]
        assert any(k in reason for k in ["subjects<", "sites<", "age_span<"])


def test_manifest_and_metadata_traceability():
    m_fields, m_rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
    for col in [
        "dataset_id",
        "snapshot_tag",
        "subject_id",
        "session",
        "run",
        "remote_relpath",
        "local_path",
        "bytes",
        "sha256",
    ]:
        assert col in m_fields

    for r in m_rows:
        assert r["dataset_id"] == "ds000030"
        assert r["subject_id"].startswith("sub-")
        assert int(r["bytes"]) > 0
        s = r["sha256"].strip().lower()
        assert len(s) == 64
        int(s, 16)

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta.get("task_id") == "OPENNEURO-SA-010"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds000030"
    assert meta.get("status") in {"ok", "failed_precondition"}
    assert str(meta.get("reason", "")).strip()
    assert str(meta.get("snapshot_tag", "")).strip()
    assert meta.get("method") == "real_bold_quadratic_age_model"

    assert int(meta.get("subjects_included", -1)) >= 0
    assert int(meta.get("sites_included", -1)) >= 1
    assert float(meta.get("age_span", -1.0)) >= 0.0
    assert int(meta.get("processing_run_count", -1)) >= 0

    assert int(meta.get("input_file_count", -1)) == len(m_rows)
    assert int(meta.get("input_bytes_total", -1)) == sum(int(r["bytes"]) for r in m_rows)

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha
    assert int(meta.get("records_count", -1)) == 2
    assert int(meta.get("bytes_total", -1)) > 0

    _, rows = _read_csv(OUTPUT_DIR / "age_model_results.csv")
    row = rows[0]
    assert meta.get("status") == row["status"]
    assert meta.get("reason") == row["reason"]
    assert meta.get("snapshot_tag") == row["snapshot_tag"]

    if row["status"] == "ok":
        assert len(m_rows) > 0
        assert int(row["runs_used"]) > 0
