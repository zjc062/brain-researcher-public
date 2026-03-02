import csv
import hashlib
import json
import os
from pathlib import Path

import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
MIN_EVENT_SAMPLES = 3


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
    for name in ["effect_sizes.csv", "input_manifest.csv", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_effect_sizes_schema_and_status_contract():
    fields, rows = _read_csv(OUTPUT_DIR / "effect_sizes.csv")
    for col in [
        "stimulus_id",
        "cohens_d",
        "ci_lower",
        "ci_upper",
        "n_samples",
        "mean_effect",
        "status",
        "reason",
        "subjects_included",
        "runs_used",
        "events_used",
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

    if status == "ok":
        for r in rows:
            assert r["status"] == "ok"
            assert r["reason"] == "computed"
            assert r["stimulus_id"] != "ALL"
            d = float(r["cohens_d"])
            lo = float(r["ci_lower"])
            hi = float(r["ci_upper"])
            n = int(r["n_samples"])
            m = float(r["mean_effect"])
            assert np.isfinite(d)
            assert np.isfinite(lo)
            assert np.isfinite(hi)
            assert np.isfinite(m)
            assert lo <= d <= hi
            assert n >= MIN_EVENT_SAMPLES
            assert int(r["subjects_included"]) >= 1
            assert int(r["runs_used"]) >= 1
            assert int(r["events_used"]) >= n
            assert r["dataset_id"] == "ds000255"
            assert r["method"] == "real_bold_event_effect_size"
    else:
        assert status == "failed_precondition"
        assert len(rows) == 1
        row = rows[0]
        assert row["stimulus_id"] == "ALL"
        assert row["cohens_d"] == "NA"
        assert row["ci_lower"] == "NA"
        assert row["ci_upper"] == "NA"
        assert row["n_samples"] == "0"
        assert row["mean_effect"] == "NA"
        assert row["method"] == "real_bold_event_effect_size"
        assert row["dataset_id"] == "ds000255"
        assert reason.strip()


def test_manifest_and_metadata_traceability():
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

    for r in m_rows:
        assert r["dataset_id"] == "ds000255"
        assert r["subject_id"].startswith("sub-")
        assert int(r["bold_bytes"]) > 0
        assert int(r["events_bytes"]) > 0
        bsha = r["bold_sha256"].strip().lower()
        esha = r["events_sha256"].strip().lower()
        assert len(bsha) == 64
        assert len(esha) == 64
        int(bsha, 16)
        int(esha, 16)

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta.get("task_id") == "OPENNEURO-SA-007"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds000255"
    assert meta.get("status") in {"ok", "failed_precondition"}
    assert str(meta.get("reason", "")).strip()
    assert str(meta.get("snapshot_tag", "")).strip()
    assert meta.get("method") == "real_bold_event_effect_size"

    assert int(meta.get("processing_subject_count", -1)) >= 0
    assert int(meta.get("processing_run_count", -1)) >= 0
    assert int(meta.get("events_used", -1)) >= 0

    assert int(meta.get("input_file_count", -1)) == len(m_rows) * 2
    assert int(meta.get("input_bytes_total", -1)) == sum(
        int(r["bold_bytes"]) + int(r["events_bytes"]) for r in m_rows
    )

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha
    assert int(meta.get("records_count", -1)) == 2
    assert int(meta.get("bytes_total", -1)) > 0

    _, rows = _read_csv(OUTPUT_DIR / "effect_sizes.csv")
    csv_status = rows[0]["status"]
    csv_reason = rows[0]["reason"]
    csv_snapshot = rows[0]["snapshot_tag"]
    assert meta.get("status") == csv_status
    assert meta.get("reason") == csv_reason
    assert meta.get("snapshot_tag") == csv_snapshot

    if csv_status == "ok":
        assert len(m_rows) > 0
        assert int(meta.get("processing_run_count", 0)) > 0
