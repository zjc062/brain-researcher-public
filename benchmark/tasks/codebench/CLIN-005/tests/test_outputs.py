import csv
import json
import os
from pathlib import Path

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["predicted_ages.csv", "age_gap_distribution.png"]
OUTPUT_SCHEMA = {
    "predicted_ages.csv": {
        "type": "csv",
        "required_columns": [
            "subject_id",
            "chronological_age",
            "predicted_age",
            "brain_age_gap",
            "split",
        ],
    },
    "age_gap_distribution.png": {"type": "png", "min_size_px": [200, 200]},
}
METRIC_VALIDATION = {}

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None, f"CSV header missing: {path}"
        rows = list(reader)
    return reader.fieldnames, rows


def _to_float(value):
    return float(str(value).strip())


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Required output is not a file: {p}"


def test_predicted_ages_schema_and_semantics():
    fieldnames, rows = _read_csv(OUTPUT_DIR / "predicted_ages.csv")
    for col in OUTPUT_SCHEMA["predicted_ages.csv"]["required_columns"]:
        assert col in fieldnames, f"Missing required column: {col}"
    assert rows, "predicted_ages.csv must not be empty"

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()
    assert status in {"ok", "failed_precondition"}

    if status == "ok":
        assert len(rows) >= 20, "Need at least 20 subjects in predicted_ages.csv for ok mode"
        for row in rows:
            sid = row["subject_id"].strip()
            assert sid, "subject_id cannot be empty"

            age = _to_float(row["chronological_age"])
            pred = _to_float(row["predicted_age"])
            gap = _to_float(row["brain_age_gap"])
            split = row["split"].strip().lower()

            assert 0.0 <= age <= 120.0
            assert 0.0 <= pred <= 120.0
            assert split in {"train", "test"}
            assert abs((pred - age) - gap) <= 1e-6
    else:
        assert len(rows) >= 1
        assert rows[0]["split"].strip().lower() == "failed_precondition"


def test_age_gap_distribution_png_not_placeholder():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()

    png = OUTPUT_DIR / "age_gap_distribution.png"
    data = png.read_bytes()
    assert data.startswith(PNG_MAGIC), "age_gap_distribution.png is not a PNG file"
    if status == "ok":
        assert len(data) > 5_000, "age_gap_distribution.png appears too small"
    else:
        assert len(data) > 800, "age_gap_distribution.png appears invalid in fail-fast mode"


def test_traceability_with_run_metadata():
    meta_path = OUTPUT_DIR / "run_metadata.json"
    assert meta_path.exists(), "run_metadata.json is required"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta.get("task_id") == "CLIN-005"
    assert meta.get("dataset_source") == "Nilearn"
    assert meta.get("dataset_id") == "fetch_oasis_vbm"
    assert str(meta.get("reason", "")).strip()

    status = str(meta.get("status", "")).strip().lower()
    assert status in {"ok", "failed_precondition"}

    assert str(meta.get("model_name", "")).strip() == "oasis_feature_ridge_regression"
    if status == "ok":
        assert str(meta.get("model_version", "")).strip()
    assert str(meta.get("model_source_type", "")).strip() in {"derived_from_input", ""}
    assert str(meta.get("model_source", "")).strip()

    _, rows = _read_csv(OUTPUT_DIR / "predicted_ages.csv")

    if status == "ok":
        assert int(meta.get("n_subjects_total")) == len(rows)

        gap_values = [_to_float(r["brain_age_gap"]) for r in rows]
        gap_mean = sum(gap_values) / len(gap_values)
        assert abs(gap_mean - float(meta.get("brain_age_gap_mean"))) <= 1e-6

        splits = [r["split"].strip().lower() for r in rows]
        assert int(meta.get("n_subjects_train")) == splits.count("train")
        assert int(meta.get("n_subjects_test")) == splits.count("test")
    else:
        assert int(meta.get("n_subjects_total", 0)) == 0
