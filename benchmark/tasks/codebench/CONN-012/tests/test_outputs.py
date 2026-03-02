import csv
import json
import os
from pathlib import Path

import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["significant_edges.csv", "edge_statistics.npy"]
OUTPUT_SCHEMA = {
    "significant_edges.csv": {
        "type": "csv",
        "required_columns": [
            "edge_i",
            "edge_j",
            "t_stat",
            "p_value",
            "mean_asd",
            "mean_control",
            "effect_size",
            "significant",
        ],
    },
    "edge_statistics.npy": {"type": "file"},
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


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        path = OUTPUT_DIR / name
        assert path.exists(), f"Missing required output: {path}"
        assert path.is_file(), f"Required output is not a file: {path}"


def test_run_metadata_contract():
    meta = _read_meta()
    assert meta.get("task_id") == "CONN-012"
    assert meta.get("dataset_source") == "Nilearn"
    assert meta.get("dataset_id") == "fetch_abide_pcp"

    status = str(meta.get("status", "")).strip().lower()
    reason = str(meta.get("reason", "")).strip()
    assert status in {"ok", "failed_precondition"}
    assert reason


def test_significant_edges_schema_and_ranges():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()

    fieldnames, rows = _read_csv(OUTPUT_DIR / "significant_edges.csv")
    for col in OUTPUT_SCHEMA["significant_edges.csv"]["required_columns"]:
        assert col in fieldnames, f"Missing required column: {col}"

    assert rows, "significant_edges.csv must not be empty"

    prev_p = -1.0
    for row in rows:
        edge_i = _to_int(row["edge_i"])
        edge_j = _to_int(row["edge_j"])
        t_stat = _to_float(row["t_stat"])
        p_value = _to_float(row["p_value"])
        mean_asd = _to_float(row["mean_asd"])
        mean_control = _to_float(row["mean_control"])
        effect_size = _to_float(row["effect_size"])
        significant = _to_int(row["significant"])

        assert edge_i >= 0 and edge_j >= 0 and edge_i != edge_j
        assert np.isfinite(t_stat)
        assert 0.0 <= p_value <= 1.0
        assert np.isfinite(mean_asd)
        assert np.isfinite(mean_control)
        assert np.isfinite(effect_size)
        assert significant in (0, 1)
        if significant == 1:
            assert p_value <= 0.05 + 1e-12

        if status == "ok":
            assert p_value + 1e-12 >= prev_p, "Rows must be sorted by ascending p-value"
        prev_p = p_value


def test_edge_statistics_matrix_semantics():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()

    mat = np.load(OUTPUT_DIR / "edge_statistics.npy")
    assert mat.ndim == 2, "edge_statistics.npy must be 2D"
    assert mat.shape[0] == mat.shape[1], "edge_statistics matrix must be square"
    assert np.all(np.isfinite(mat)), "edge_statistics matrix contains non-finite values"

    if status == "ok":
        assert mat.shape[0] >= 10, "edge_statistics matrix appears too small"
        assert np.allclose(mat, mat.T, atol=1e-6), "edge_statistics matrix must be symmetric"
        assert np.allclose(np.diag(mat), 0.0, atol=1e-8), "Diagonal must be zero"
    else:
        assert mat.shape[0] >= 2


def test_cross_file_consistency_with_run_metadata():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()
    if status != "ok":
        return

    mat = np.load(OUTPUT_DIR / "edge_statistics.npy")
    n_regions = int(meta.get("n_regions"))
    assert mat.shape == (n_regions, n_regions)

    _, rows = _read_csv(OUTPUT_DIR / "significant_edges.csv")
    assert int(meta.get("n_reported_edges")) == len(rows)

    for row in rows:
        i = _to_int(row["edge_i"])
        j = _to_int(row["edge_j"])
        t_stat = _to_float(row["t_stat"])

        assert 0 <= i < n_regions
        assert 0 <= j < n_regions
        assert i != j
        assert abs(t_stat - float(mat[i, j])) <= 1e-6

    n_sig_csv = sum(_to_int(r["significant"]) for r in rows)
    assert int(meta.get("n_significant")) >= n_sig_csv
    assert int(meta.get("n_subjects_asd")) >= 2
    assert int(meta.get("n_subjects_control")) >= 2
    assert int(meta.get("n_edges_total")) == n_regions * (n_regions - 1) // 2
