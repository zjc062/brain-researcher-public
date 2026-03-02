import csv
import hashlib
import json
import os
from pathlib import Path

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
    for name in ["anatomical_qc.csv", "input_manifest.csv", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_qc_csv_schema_and_status_contract():
    fields, rows = _read_csv(OUTPUT_DIR / "anatomical_qc.csv")
    for col in [
        "subject_id",
        "snr",
        "cnr",
        "qi1",
        "overall_rating",
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
        assert r["dataset_id"] == "ds002424"
        assert r["method"] == "real_t1w_intensity_qc"
        assert str(r["snapshot_tag"]).strip()
        assert r["status"] == status
        assert r["reason"] == rows[0]["reason"]

    if status == "ok":
        ids = [r["subject_id"] for r in rows]
        assert all(i.startswith("sub-") for i in ids)
        assert len(ids) == len(set(ids))

        rating_set = {r["overall_rating"] for r in rows}
        assert rating_set.issubset({"pass", "warn", "fail"})

        for r in rows:
            snr = float(r["snr"])
            cnr = float(r["cnr"])
            qi1 = float(r["qi1"])
            assert np.isfinite(snr) and snr > 0.0
            assert np.isfinite(cnr)
            assert np.isfinite(qi1) and 0.0 <= qi1 <= 1.0

        assert len(rows) >= 1
    else:
        assert status == "failed_precondition"
        for r in rows:
            assert r["subject_id"] == "NA"
            assert r["snr"] == "NA"
            assert r["cnr"] == "NA"
            assert r["qi1"] == "NA"
            assert r["overall_rating"] == "fail"


def test_manifest_and_metadata_consistency():
    m_fields, m_rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
    for col in [
        "dataset_id",
        "snapshot_tag",
        "subject_id",
        "session",
        "anat_relpath",
        "local_path",
        "bytes",
        "sha256",
    ]:
        assert col in m_fields

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    _, q_rows = _read_csv(OUTPUT_DIR / "anatomical_qc.csv")

    assert meta.get("task_id") == "OPENNEURO-QC-003"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds002424"
    assert meta.get("status") in {"ok", "failed_precondition"}
    assert str(meta.get("reason", "")).strip()
    assert str(meta.get("snapshot_tag", "")).strip()
    assert meta.get("method") == "real_t1w_intensity_qc"

    assert meta.get("status") == q_rows[0]["status"]
    assert meta.get("reason") == q_rows[0]["reason"]

    for r in m_rows:
        assert r["dataset_id"] == "ds002424"
        assert r["subject_id"].startswith("sub-")
        assert str(r["anat_relpath"]).strip().endswith((".nii", ".nii.gz"))
        assert int(r["bytes"]) > 0
        s = r["sha256"].strip().lower()
        assert len(s) == 64
        int(s, 16)

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha

    assert int(meta.get("processing_run_count", -1)) == len(m_rows)
    assert int(meta.get("input_file_count", -1)) == len(m_rows)
    assert int(meta.get("input_bytes_total", -1)) == sum(int(r["bytes"]) for r in m_rows)

    if meta.get("status") == "ok":
        assert int(meta.get("processing_subject_count", -1)) == len(q_rows)
        assert len(m_rows) >= 1
    else:
        assert int(meta.get("processing_subject_count", -1)) == 0

    assert int(meta.get("records_count", -1)) == 3
    assert int(meta.get("bytes_total", -1)) > 0
