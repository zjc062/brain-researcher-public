import csv
import json
import os
from pathlib import Path

import matplotlib.image as mpimg
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["structural_connectome.csv", "connectome_plot.png"]
OUTPUT_SCHEMA = {
    "structural_connectome.csv": {
        "type": "csv",
        "required_columns": [
            "region_i",
            "region_j",
            "index_i",
            "index_j",
            "weight",
            "mean_fa_i",
            "mean_fa_j",
            "n_voxels_i",
            "n_voxels_j",
        ],
    },
    "connectome_plot.png": {"type": "png", "min_size_px": [300, 300]},
}
METRIC_VALIDATION = {}


def _read_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames is not None, f"CSV header missing: {path}"
        rows = list(reader)
    return reader.fieldnames, rows


def _to_int(v):
    return int(float(str(v).strip()))


def _to_float(v):
    return float(str(v).strip())


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Required output is not a file: {p}"



def test_run_metadata_contract():
    meta_path = OUTPUT_DIR / "run_metadata.json"
    assert meta_path.exists(), "run_metadata.json is required"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta.get("task_id") == "DIFF-005"
    assert meta.get("dataset_source") == "Provided"
    assert meta.get("dataset_id") == "custom_dwi_aal_atlas"

    status = str(meta.get("status", "")).strip().lower()
    reason = str(meta.get("reason", "")).strip()
    assert status in {"ok", "failed_precondition"}
    assert reason
    assert int(meta.get("records_count", 0)) >= 0
    assert int(meta.get("bytes_total", 0)) >= 0



def test_connectome_csv_schema_and_values():
    fieldnames, rows = _read_csv(OUTPUT_DIR / "structural_connectome.csv")
    for col in OUTPUT_SCHEMA["structural_connectome.csv"]["required_columns"]:
        assert col in fieldnames, f"Missing required column: {col}"

    assert len(rows) >= 1
    for row in rows:
        idx_i = _to_int(row["index_i"])
        idx_j = _to_int(row["index_j"])
        weight = _to_float(row["weight"])
        fa_i = _to_float(row["mean_fa_i"])
        fa_j = _to_float(row["mean_fa_j"])
        n_i = _to_int(row["n_voxels_i"])
        n_j = _to_int(row["n_voxels_j"])

        assert np.isfinite(weight)
        assert np.isfinite(fa_i)
        assert np.isfinite(fa_j)
        assert idx_i >= 0 and idx_j >= 0
        assert n_i >= 0 and n_j >= 0



def test_plot_is_valid_png_and_large_enough():
    img = mpimg.imread(OUTPUT_DIR / "connectome_plot.png")
    assert img.ndim in {2, 3}
    h, w = int(img.shape[0]), int(img.shape[1])
    assert h >= 300 and w >= 300, f"Plot too small: {(h, w)}"



def test_cross_file_traceability_and_semantics():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()

    _, rows = _read_csv(OUTPUT_DIR / "structural_connectome.csv")

    if status == "ok":
        assert len(rows) >= 3, "Need at least 3 connectome edges in ok mode"

        input_path = Path(str(meta.get("input_dwi_path", "")))
        atlas_path = Path(str(meta.get("input_atlas_path", "")))
        assert input_path.exists(), "input_dwi_path in run_metadata must exist"
        assert atlas_path.exists(), "input_atlas_path in run_metadata must exist"

        region_set = set()
        for row in rows:
            region_set.add(str(row["region_i"]))
            region_set.add(str(row["region_j"]))
            assert str(row["region_i"]) != str(row["region_j"])

        n_edges = int(meta.get("n_edges", -1))
        n_regions = int(meta.get("n_regions", -1))
        mean_edge = float(meta.get("mean_edge_weight", -1.0))

        assert n_edges == len(rows)
        assert n_regions == len(region_set)
        assert mean_edge >= 0.0

        csv_mean = float(np.mean([_to_float(r["weight"]) for r in rows]))
        assert abs(csv_mean - mean_edge) < 1e-5
    else:
        assert status == "failed_precondition"

