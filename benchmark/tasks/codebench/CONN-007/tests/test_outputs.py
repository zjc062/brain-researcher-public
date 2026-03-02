import csv
import json
import os
from pathlib import Path

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["graph_metrics.csv", "small_world_sigma.txt"]
OUTPUT_SCHEMA = {
    "graph_metrics.csv": {
        "type": "csv",
        "required_columns": [
            "subject_id",
            "dx_group",
            "mean_degree",
            "density",
            "clustering_coeff",
            "path_length",
        ],
    },
    "small_world_sigma.txt": {"type": "text"},
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
    assert meta.get("task_id") == "CONN-007"
    assert meta.get("dataset_source") == "Nilearn"
    assert meta.get("dataset_id") == "fetch_abide_pcp"

    status = str(meta.get("status", "")).strip().lower()
    reason = str(meta.get("reason", "")).strip()
    assert status in {"ok", "failed_precondition"}
    assert reason


def test_graph_metrics_schema_and_ranges():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()

    fieldnames, rows = _read_csv(OUTPUT_DIR / "graph_metrics.csv")
    for column in OUTPUT_SCHEMA["graph_metrics.csv"]["required_columns"]:
        assert column in fieldnames, f"Missing required column: {column}"

    assert rows, "graph_metrics.csv should not be empty"
    if status != "ok":
        return

    assert len(rows) >= 4, "graph_metrics.csv should include >= 4 subjects"

    groups = sorted({_to_int(r["dx_group"]) for r in rows})
    assert groups == [1, 2], f"Expected both groups [1,2], got {groups}"

    for row in rows:
        assert row["subject_id"].startswith("sub-"), f"Invalid subject_id: {row['subject_id']}"
        mean_degree = _to_float(row["mean_degree"])
        density = _to_float(row["density"])
        clustering = _to_float(row["clustering_coeff"])
        path_length = _to_float(row["path_length"])

        assert mean_degree >= 0.0
        assert 0.0 <= density <= 1.0
        assert 0.0 <= clustering <= 1.0
        assert path_length > 0.0


def test_small_world_sigma_valid():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()

    sigma_text = (OUTPUT_DIR / "small_world_sigma.txt").read_text(encoding="utf-8").strip()
    sigma = float(sigma_text)
    if status == "ok":
        assert sigma > 0.0
        assert sigma < 100.0
    else:
        assert sigma >= 0.0


def test_semantic_consistency_with_run_metadata():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()
    if status != "ok":
        return

    _, rows = _read_csv(OUTPUT_DIR / "graph_metrics.csv")
    assert int(meta.get("n_subjects")) == len(rows)

    counts = {"1": 0, "2": 0}
    for row in rows:
        counts[str(_to_int(row["dx_group"]))] += 1
    assert counts == meta.get("group_subject_counts")

    sigma_txt = float((OUTPUT_DIR / "small_world_sigma.txt").read_text(encoding="utf-8").strip())
    sigma_meta = float(meta.get("sigma"))
    assert abs(sigma_txt - sigma_meta) <= 1e-6

    c_obs = float(meta.get("c_obs"))
    l_obs = float(meta.get("l_obs"))
    c_rand = float(meta.get("c_rand"))
    l_rand = float(meta.get("l_rand"))
    recomputed = (c_obs / c_rand) / (l_obs / l_rand)
    assert abs(recomputed - sigma_txt) <= 1e-6
