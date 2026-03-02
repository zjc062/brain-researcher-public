import csv
import json
import os
import re
from pathlib import Path

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["qa_report.html", "flagged_subjects.csv"]
OUTPUT_SCHEMA = {
    "qa_report.html": {"type": "html"},
    "flagged_subjects.csv": {
        "type": "csv",
        "required_columns": [
            "subject_id",
            "issue_code",
            "severity",
            "metric_name",
            "metric_value",
            "threshold",
            "details",
            "gm_path",
            "wm_path",
        ],
    },
}
METRIC_VALIDATION = {}


def _read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None, f"Missing CSV header: {path}"
        rows = list(reader)
    return reader.fieldnames, rows


def _safe_float(v):
    return float(str(v).strip())


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        path = OUTPUT_DIR / name
        assert path.exists(), f"Missing required output: {path}"
        assert path.is_file(), f"Required output is not a file: {path}"


def test_run_metadata_contract():
    meta_path = OUTPUT_DIR / "run_metadata.json"
    assert meta_path.exists(), "run_metadata.json is required"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    required = [
        "task_id",
        "dataset_source",
        "dataset_id",
        "status",
        "reason",
        "n_subjects_total",
        "n_flagged_rows",
        "n_unique_flagged_subjects",
        "used_subject_ids",
    ]
    for key in required:
        assert key in meta, f"Missing run_metadata key: {key}"

    assert meta["task_id"] == "DATA-016"
    assert meta["dataset_source"] == "Nilearn"
    assert meta["dataset_id"] == "fetch_oasis_vbm"
    assert meta["status"] in {"ok", "failed_precondition"}
    assert isinstance(meta["reason"], str) and meta["reason"].strip()
    assert int(meta["n_subjects_total"]) >= 0
    assert int(meta["n_flagged_rows"]) >= 0
    assert int(meta["n_unique_flagged_subjects"]) >= 0

    if meta["status"] == "ok":
        assert int(meta["n_subjects_total"]) > 0
        assert len(meta.get("used_subject_ids") or []) == int(meta["n_subjects_total"])


def test_flagged_subjects_schema_and_values():
    fieldnames, rows = _read_csv(OUTPUT_DIR / "flagged_subjects.csv")
    required_cols = OUTPUT_SCHEMA["flagged_subjects.csv"]["required_columns"]
    for col in required_cols:
        assert col in fieldnames, f"Missing CSV column: {col}"

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert len(rows) == int(meta["n_flagged_rows"])

    allowed_issue_codes = {
        "missing_modality",
        "low_signal",
        "intensity_outlier",
        "shape_mismatch",
        "registration_outlier",
        "precondition_failure",
    }
    allowed_severity = {"warn", "error"}
    sid_pattern = re.compile(r"^(OAS1_\d{4}_MR1|sub-[A-Za-z0-9][A-Za-z0-9_-]*|N/A)$")

    for row in rows:
        assert row["issue_code"] in allowed_issue_codes
        assert row["severity"] in allowed_severity
        assert sid_pattern.match(row["subject_id"]), f"Unexpected subject_id: {row['subject_id']}"
        assert row["metric_name"].strip()
        assert row["threshold"].strip()
        assert row["details"].strip()
        _safe_float(row["metric_value"])

    if meta["status"] == "failed_precondition":
        assert rows, "failed_precondition must produce explicit failure row"
        assert any(r["issue_code"] == "precondition_failure" for r in rows)
    else:
        used = set(meta.get("used_subject_ids") or [])
        flagged_subjects = {r["subject_id"] for r in rows if r["subject_id"] != "N/A"}
        assert flagged_subjects.issubset(used)


def test_html_report_has_summary():
    html_text = (OUTPUT_DIR / "qa_report.html").read_text(encoding="utf-8", errors="ignore")
    lower = html_text.lower()

    assert "<html" in lower and "<body" in lower
    assert "oasis vbm qa report" in lower
    assert "total subjects analyzed" in lower
    assert "flagged rows" in lower

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert str(meta["status"]) in html_text
    assert str(meta["reason"]) in html_text
