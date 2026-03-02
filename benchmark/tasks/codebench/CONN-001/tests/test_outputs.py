import csv
import json
import os
from pathlib import Path

import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["connectivity_matrix.npy", "group_comparison.csv"]
OUTPUT_SCHEMA = {
    "connectivity_matrix.npy": {"type": "file"},
    "group_comparison.csv": {
        "type": "csv",
        "required_columns": [
            "group_label",
            "dx_group",
            "n_subjects",
            "mean_edge_connectivity",
            "std_edge_connectivity",
            "subject_ids",
        ],
    },
}
METRIC_VALIDATION = {}


def _read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None, f"CSV header missing: {path}"
        rows = list(reader)
    return reader.fieldnames, rows


def _read_meta() -> dict:
    meta_path = OUTPUT_DIR / "run_metadata.json"
    assert meta_path.exists(), "run_metadata.json is required for traceability"
    return json.loads(meta_path.read_text(encoding="utf-8"))


def _to_int(value):
    return int(str(value).strip())


def _to_float(value):
    return float(str(value).strip())


def _parse_subjects(cell: str) -> list[str]:
    return [item.strip() for item in str(cell).split(";") if item.strip()]


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        path = OUTPUT_DIR / name
        assert path.exists(), f"Missing required output: {path}"
        assert path.is_file(), f"Required output is not a file: {path}"


def test_run_metadata_contract():
    meta = _read_meta()
    assert meta.get("task_id") == "CONN-001"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds002424"

    status = str(meta.get("status", "")).strip().lower()
    reason = str(meta.get("reason", "")).strip()
    assert status in {"ok", "failed_precondition"}
    assert reason


def test_group_comparison_schema_and_groups():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()

    path = OUTPUT_DIR / "group_comparison.csv"
    fieldnames, rows = _read_csv(path)

    for column in OUTPUT_SCHEMA["group_comparison.csv"]["required_columns"]:
        assert column in fieldnames, f"Missing required CSV column {column!r}"

    assert rows, "group_comparison.csv must not be empty"
    if status != "ok":
        return

    assert len(rows) == 2, "group_comparison.csv must have exactly two rows (control and adhd)"

    dx_values = sorted(_to_int(row["dx_group"]) for row in rows)
    assert dx_values == [0, 1], f"dx_group must be [0,1], got {dx_values}"

    for row in rows:
        n_subjects = _to_int(row["n_subjects"])
        assert n_subjects >= 1, "Each group must include at least one subject"

        mean_edge = _to_float(row["mean_edge_connectivity"])
        std_edge = _to_float(row["std_edge_connectivity"])
        assert -1.0 <= mean_edge <= 1.0, f"mean_edge_connectivity out of range: {mean_edge}"
        assert std_edge >= 0.0, f"std_edge_connectivity must be non-negative: {std_edge}"

        subject_ids = _parse_subjects(row["subject_ids"])
        assert len(subject_ids) == n_subjects, "subject_ids count must match n_subjects"
        for subject_id in subject_ids:
            assert subject_id.startswith("sub-"), f"Invalid subject_id format: {subject_id}"


def test_connectivity_matrix_semantics():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()

    matrix = np.load(OUTPUT_DIR / "connectivity_matrix.npy")
    assert matrix.ndim == 2, "connectivity_matrix.npy must be 2D"
    assert matrix.shape[0] == matrix.shape[1], "connectivity matrix must be square"
    assert np.all(np.isfinite(matrix)), "connectivity matrix contains non-finite values"

    if status != "ok":
        assert matrix.shape[0] >= 2
        return

    assert matrix.shape[0] >= 10, "connectivity matrix appears too small"
    assert np.allclose(matrix, matrix.T, atol=1e-6), "connectivity matrix must be symmetric"
    diag = np.diag(matrix)
    assert np.allclose(diag, 1.0, atol=1e-2), "matrix diagonal must be approximately 1"


def test_cross_file_traceability_and_consistency():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()
    if status != "ok":
        return

    used_subjects = sorted(meta.get("used_subject_ids") or [])
    assert used_subjects, "run_metadata.used_subject_ids must be non-empty"

    for file_path in meta.get("used_file_paths") or []:
        assert Path(file_path).exists(), f"Referenced file path does not exist: {file_path}"

    _, rows = _read_csv(OUTPUT_DIR / "group_comparison.csv")
    csv_subjects = []
    for row in rows:
        csv_subjects.extend(_parse_subjects(row["subject_ids"]))
    csv_subjects = sorted(csv_subjects)

    assert csv_subjects == used_subjects, "group_comparison subject_ids must match run_metadata"

    matrix = np.load(OUTPUT_DIR / "connectivity_matrix.npy")
    upper_mean = float(np.mean(matrix[np.triu_indices_from(matrix, k=1)]))
    assert abs(upper_mean - float(meta.get("matrix_upper_mean"))) <= 1e-6
