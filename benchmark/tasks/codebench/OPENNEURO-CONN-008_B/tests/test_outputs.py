import csv
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_SUBJECTS = 10
REQUIRED_REPEAT_SUBJECTS = 10


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
    for name in ["icc_results.csv", "reliability_map.nii.gz", "input_manifest.csv", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_input_manifest_counts_and_schema():
    fields, rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
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
        assert col in fields

    assert rows
    counts = Counter()
    for r in rows:
        assert r["dataset_id"] == "ds000030"
        assert r["subject_id"].startswith("sub-")
        counts[r["subject_id"]] += 1
        assert int(r["bytes"]) > 0
        s = r["sha256"].strip().lower()
        assert len(s) == 64
        int(s, 16)

    subject_count = len(counts)
    repeat_count = sum(1 for _, c in counts.items() if c >= 2)
    bold_count = sum(counts.values())
    assert subject_count >= 1
    assert repeat_count >= 1
    assert bold_count >= 1


def test_icc_table_matches_precondition_logic():
    _, manifest_rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
    counts = Counter(r["subject_id"] for r in manifest_rows)
    n_subjects = len(counts)
    n_repeat = sum(1 for _, c in counts.items() if c >= 2)
    n_bold = sum(counts.values())

    reasons = []
    if n_subjects < REQUIRED_SUBJECTS:
        reasons.append(f"subjects<{REQUIRED_SUBJECTS}")
    if n_repeat < REQUIRED_REPEAT_SUBJECTS:
        reasons.append(f"repeat_subjects<{REQUIRED_REPEAT_SUBJECTS}")
    if n_bold == 0:
        reasons.append("bold_files==0")

    fields, rows = _read_csv(OUTPUT_DIR / "icc_results.csv")
    for col in [
        "connection_id",
        "icc_value",
        "ci_95_low",
        "ci_95_high",
        "mean_icc",
        "status",
        "reason",
        "subjects_included",
        "repeat_subjects",
        "bold_files",
        "dataset_id",
        "snapshot_tag",
        "method",
    ]:
        assert col in fields

    assert rows
    status = rows[0]["status"]

    if reasons:
        assert status == "failed_precondition"
        assert len(rows) == 1
        for reason in reasons:
            assert reason in rows[0]["reason"]
        assert rows[0]["icc_value"] == "NA"
        assert rows[0]["ci_95_low"] == "NA"
        assert rows[0]["ci_95_high"] == "NA"
        assert rows[0]["mean_icc"] == "NA"
    else:
        assert status == "ok"
        for r in rows:
            assert r["status"] == "ok"
            assert r["reason"] == "preconditions_met"
            icc = float(r["icc_value"])
            lo = float(r["ci_95_low"])
            hi = float(r["ci_95_high"])
            mean_icc = float(r["mean_icc"])
            assert -1.0 <= lo <= hi <= 1.0
            assert -1.0 <= icc <= 1.0
            assert -1.0 <= mean_icc <= 1.0

    for r in rows:
        assert int(r["subjects_included"]) == n_subjects
        assert int(r["repeat_subjects"]) == n_repeat
        assert int(r["bold_files"]) == n_bold
        assert r["dataset_id"] == "ds000030"


def test_reliability_map_and_metadata_traceability():
    img = nib.load(str(OUTPUT_DIR / "reliability_map.nii.gz"))
    arr = np.asarray(img.get_fdata(), dtype=float)
    assert arr.ndim == 3
    assert np.isfinite(arr).all()
    assert float(np.std(arr)) > 1e-8

    _, manifest_rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
    counts = Counter(r["subject_id"] for r in manifest_rows)
    n_subjects = len(counts)
    n_repeat = sum(1 for _, c in counts.items() if c >= 2)
    n_bold = sum(counts.values())

    _, icc_rows = _read_csv(OUTPUT_DIR / "icc_results.csv")
    csv_status = icc_rows[0]["status"]
    csv_reason = icc_rows[0]["reason"]

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta.get("task_id") == "OPENNEURO-CONN-008_B"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds000030"
    assert meta.get("status") == csv_status
    assert meta.get("reason") == csv_reason
    assert int(meta.get("subjects_included", -1)) == n_subjects
    assert int(meta.get("repeat_subjects", -1)) == n_repeat
    assert int(meta.get("bold_files", -1)) == n_bold

    assert int(meta.get("input_file_count", -1)) == len(manifest_rows)
    assert int(meta.get("input_bytes_total", -1)) == sum(int(r["bytes"]) for r in manifest_rows)
    assert int(meta.get("records_count", -1)) == len(icc_rows)
    assert int(meta.get("bytes_total", -1)) > 0

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha
