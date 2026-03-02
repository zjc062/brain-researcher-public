import csv
import hashlib
import json
import os
from pathlib import Path

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
    for name in ["top_features.csv", "input_manifest.csv", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_top_features_schema_and_semantics():
    fields, rows = _read_csv(OUTPUT_DIR / "top_features.csv")
    for col in ["roi_1", "roi_2", "weight", "dataset_id", "snapshot_tag", "subjects_used", "best_c", "best_l1_ratio", "mean_auc"]:
        assert col in fields

    assert len(rows) == 50

    seen = set()
    abs_weights = []
    snapshot_tags = set()
    for r in rows:
        pair = (r["roi_1"], r["roi_2"])
        assert pair[0]
        assert pair[1]
        assert pair[0] != pair[1]
        assert pair not in seen
        seen.add(pair)

        w = float(r["weight"])
        assert abs(w) > 1e-12
        abs_weights.append(abs(w))

        assert r["dataset_id"] == "ds002424"
        assert int(float(r["subjects_used"])) >= 40
        assert float(r["best_c"]) > 0.0
        l1 = float(r["best_l1_ratio"])
        assert 0.0 <= l1 <= 1.0
        auc = float(r["mean_auc"])
        assert 0.5 <= auc <= 1.0
        snapshot_tags.add(r["snapshot_tag"])

    assert abs_weights == sorted(abs_weights, reverse=True)
    assert len(snapshot_tags) == 1


def test_manifest_and_run_metadata_consistency():
    m_fields, m_rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
    for col in ["dataset_id", "snapshot_tag", "file_relpath", "local_path", "bytes", "sha256"]:
        assert col in m_fields

    assert len(m_rows) == 1
    m = m_rows[0]
    assert m["dataset_id"] == "ds002424"
    assert m["file_relpath"] == "participants.tsv"
    assert int(m["bytes"]) > 0
    s = m["sha256"].strip().lower()
    assert len(s) == 64
    int(s, 16)

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta.get("task_id") == "OPENNEURO-ML-011"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds002424"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"

    assert str(meta.get("snapshot_tag", "")).strip() == m["snapshot_tag"]
    assert int(meta.get("n_subjects", -1)) >= 40
    assert int(meta.get("n_edge_features", -1)) >= 50
    assert int(meta.get("n_selected_features", -1)) == 50
    assert float(meta.get("mean_auc", -1.0)) >= 0.5

    assert int(meta.get("input_file_count", -1)) == 1
    assert int(meta.get("input_bytes_total", -1)) == int(m["bytes"])
    assert int(meta.get("records_count", -1)) == 2
    assert int(meta.get("bytes_total", -1)) > 0

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha
