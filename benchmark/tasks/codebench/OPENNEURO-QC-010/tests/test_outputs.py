import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
AXES = {"tx", "ty", "tz", "rx", "ry", "rz"}


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
    for name in ["motion_correlation.csv", "artifact_flag.json", "input_manifest.csv", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_motion_csv_schema_and_semantics():
    fields, rows = _read_csv(OUTPUT_DIR / "motion_correlation.csv")
    for col in [
        "subject_id",
        "run",
        "axis",
        "correlation_r",
        "p_value",
        "status",
        "reason",
        "dataset_id",
        "snapshot_tag",
        "method",
    ]:
        assert col in fields

    assert rows
    statuses = {r["status"] for r in rows}
    reasons = {r["reason"] for r in rows}
    assert len(statuses) == 1
    assert len(reasons) == 1
    status = rows[0]["status"]

    for r in rows:
        assert r["dataset_id"] == "ds000255"
        assert r["method"] == "real_bold_event_motion_proxy"
        assert str(r["snapshot_tag"]).strip()
        assert r["status"] == status
        assert r["reason"] == rows[0]["reason"]

    if status == "ok":
        assert len(rows) >= 6
        key_seen = set()
        for r in rows:
            assert r["subject_id"].startswith("sub-")
            assert str(r["run"]).strip()
            assert r["axis"] in AXES

            corr = float(r["correlation_r"])
            pval = float(r["p_value"])
            assert np.isfinite(corr)
            assert np.isfinite(pval)
            assert -1.0 <= corr <= 1.0
            assert 0.0 <= pval <= 1.0

            key = (r["subject_id"], r["run"], r["axis"])
            assert key not in key_seen
            key_seen.add(key)

        # Every processed run should have all 6 axes.
        group = {}
        for r in rows:
            group.setdefault((r["subject_id"], r["run"]), set()).add(r["axis"])
        assert group
        assert all(v == AXES for v in group.values())
    else:
        assert status == "failed_precondition"
        for r in rows:
            assert r["subject_id"] == "NA"
            assert r["run"] == "NA"
            assert r["correlation_r"] == "NA"
            assert r["p_value"] == "NA"


def test_artifact_json_consistency():
    _, rows = _read_csv(OUTPUT_DIR / "motion_correlation.csv")
    status = rows[0]["status"]
    reason = rows[0]["reason"]
    data = json.loads((OUTPUT_DIR / "artifact_flag.json").read_text(encoding="utf-8"))

    assert data.get("dataset_id") == "ds000255"
    assert str(data.get("snapshot_tag", "")).strip()
    assert data.get("method") == "real_bold_event_motion_proxy"
    assert data.get("status") == status
    assert data.get("reason") == reason

    if status == "ok":
        vals = [r for r in rows if r["correlation_r"] != "NA" and r["p_value"] != "NA"]
        sig = sum(1 for r in vals if float(r["p_value"]) < 0.05)
        max_abs = max(abs(float(r["correlation_r"])) for r in vals) if vals else 0.0
        assert int(data.get("significant_pairs", -1)) == sig
        assert bool(data.get("artifact_detected")) == (sig > 0)
        assert abs(float(data.get("max_abs_correlation", -1.0)) - max_abs) <= 1e-8
        assert int(data.get("runs_used", -1)) >= 1
        assert isinstance(data.get("subjects_included"), list) and data.get("subjects_included")
        assert data.get("axes") == sorted(list(AXES)) or set(data.get("axes") or []) == AXES
    else:
        assert int(data.get("significant_pairs", -1)) == 0
        assert bool(data.get("artifact_detected")) is False


def test_manifest_and_metadata_consistency():
    m_fields, m_rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
    for col in [
        "dataset_id",
        "snapshot_tag",
        "subject_id",
        "session",
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

    _, rows = _read_csv(OUTPUT_DIR / "motion_correlation.csv")
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))

    assert meta.get("task_id") == "OPENNEURO-QC-010"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds000255"
    assert meta.get("status") in {"ok", "failed_precondition"}
    assert str(meta.get("reason", "")).strip()
    assert str(meta.get("snapshot_tag", "")).strip()
    assert meta.get("method") == "real_bold_event_motion_proxy"

    assert meta.get("status") == rows[0]["status"]
    assert meta.get("reason") == rows[0]["reason"]

    for r in m_rows:
        assert r["dataset_id"] == "ds000255"
        assert r["subject_id"].startswith("sub-")
        assert str(r["run"]).strip()
        assert int(r["bold_bytes"]) > 0
        assert int(r["events_bytes"]) > 0
        for key in ["bold_sha256", "events_sha256"]:
            s = r[key].strip().lower()
            assert len(s) == 64
            int(s, 16)

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha

    assert int(meta.get("processing_run_count", -1)) == len(m_rows)
    assert int(meta.get("processing_subject_count", -1)) == len({r["subject_id"] for r in m_rows})
    assert int(meta.get("input_file_count", -1)) == 2 * len(m_rows)
    assert int(meta.get("input_bytes_total", -1)) == sum(int(r["bold_bytes"]) + int(r["events_bytes"]) for r in m_rows)

    if meta.get("status") == "ok":
        assert len(m_rows) >= 1
    else:
        assert len(m_rows) == 0

    assert int(meta.get("records_count", -1)) == 4
    assert int(meta.get("bytes_total", -1)) > 0
