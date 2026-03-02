import csv
import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["network_timeseries.csv", "correlation_matrix.png"]
OUTPUT_SCHEMA = {
    "network_timeseries.csv": {
        "type": "csv",
        "required_columns": [
            "subject_id",
            "timepoint",
            "network_id",
            "network_label",
            "signal",
        ],
    },
    "correlation_matrix.png": {"type": "png", "min_size_px": [200, 200]},
}
METRIC_VALIDATION = {}

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


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
    assert meta.get("task_id") == "CONN-002"
    assert meta.get("dataset_source") == "Nilearn"
    assert meta.get("dataset_id") == "fetch_surf_nki_enhanced"

    status = str(meta.get("status", "")).strip().lower()
    reason = str(meta.get("reason", "")).strip()
    assert status in {"ok", "failed_precondition"}
    assert reason


def test_network_timeseries_schema_and_coverage():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()

    fieldnames, rows = _read_csv(OUTPUT_DIR / "network_timeseries.csv")

    for col in OUTPUT_SCHEMA["network_timeseries.csv"]["required_columns"]:
        assert col in fieldnames, f"Missing required CSV column: {col}"

    assert rows, "network_timeseries.csv must not be empty"

    network_ids = sorted({_to_int(r["network_id"]) for r in rows})
    assert network_ids == [1, 2, 3, 4, 5, 6, 7], f"network_id coverage invalid: {network_ids}"

    if status != "ok":
        return

    subjects = sorted({r["subject_id"].strip() for r in rows})
    assert len(subjects) >= 3, "Need at least 3 subjects"

    by_subject_time = defaultdict(set)
    for row in rows:
        sid = row["subject_id"].strip()
        tp = _to_int(row["timepoint"])
        nid = _to_int(row["network_id"])
        value = _to_float(row["signal"])
        assert np.isfinite(value), f"Non-finite signal value for subject={sid} timepoint={tp}"
        by_subject_time[(sid, tp)].add(nid)

    complete_points = 0
    for ids in by_subject_time.values():
        assert ids.issubset(set(range(1, 8)))
        if len(ids) == 7:
            complete_points += 1
    assert complete_points >= 100, "Insufficient complete (subject,timepoint) entries"


def test_correlation_png_not_placeholder():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()

    png_path = OUTPUT_DIR / "correlation_matrix.png"
    data = png_path.read_bytes()
    assert data.startswith(PNG_MAGIC), "correlation_matrix.png is not a PNG file"

    if status == "ok":
        assert len(data) > 5_000, "correlation_matrix.png appears too small"
    else:
        assert len(data) > 500, "correlation_matrix.png appears invalid"


def test_semantic_consistency_with_run_metadata():
    meta = _read_meta()
    status = str(meta.get("status", "")).strip().lower()
    if status != "ok":
        return

    _, rows = _read_csv(OUTPUT_DIR / "network_timeseries.csv")
    subjects = sorted({r["subject_id"].strip() for r in rows})
    assert subjects == sorted(meta.get("used_subject_ids") or []), "Subject set mismatch vs run_metadata"

    grouped = defaultdict(list)
    for row in rows:
        sid = row["subject_id"].strip()
        grouped[sid].append(row)

    corr_mats = []
    for sid, srows in grouped.items():
        by_time = defaultdict(dict)
        for row in srows:
            tp = _to_int(row["timepoint"])
            nid = _to_int(row["network_id"])
            by_time[tp][nid] = _to_float(row["signal"])

        vectors = []
        for tp in sorted(by_time):
            current = by_time[tp]
            if all(nid in current for nid in range(1, 8)):
                vectors.append([current[nid] for nid in range(1, 8)])

        mat = np.asarray(vectors, dtype=float)
        assert mat.shape[0] >= 10, f"Too few complete timepoints for subject={sid}"
        corr = np.corrcoef(mat, rowvar=False)
        np.fill_diagonal(corr, 1.0)
        corr_mats.append(corr)

    mean_corr = np.mean(np.stack(corr_mats, axis=0), axis=0)
    assert mean_corr.shape == (7, 7)
    assert np.allclose(mean_corr, mean_corr.T, atol=1e-6)
    assert np.all(np.isfinite(mean_corr))

    upper_mean = float(np.mean(mean_corr[np.triu_indices_from(mean_corr, k=1)]))
    meta_upper_mean = float(meta.get("correlation_upper_mean"))
    assert abs(upper_mean - meta_upper_mean) <= 1e-6
