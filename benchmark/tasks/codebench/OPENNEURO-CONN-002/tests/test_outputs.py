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
    for name in [
        "subject_connectivity_matrices.npz",
        "dmn_summary.csv",
        "input_manifest.csv",
        "run_metadata.json",
    ]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Expected file: {p}"


def test_manifest_schema_and_hash_shape():
    fieldnames, rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
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
        assert col in fieldnames

    assert rows
    for row in rows:
        assert row["dataset_id"] == "ds001168"
        assert row["snapshot_tag"].strip()
        assert row["subject_id"].startswith("sub-")
        assert int(row["bytes"]) > 0
        s = row["sha256"].strip().lower()
        assert len(s) == 64
        int(s, 16)
        assert row["remote_relpath"].endswith(".nii.gz")


def test_npz_and_summary_consistency():
    npz = np.load(OUTPUT_DIR / "subject_connectivity_matrices.npz")
    subjects = [str(x) for x in npz["subject_ids"].tolist()]
    labels = [str(x) for x in npz["dmn_labels"].tolist()]
    mats = np.asarray(npz["matrices"], dtype=float)

    assert len(subjects) > 0
    assert len(labels) >= 2
    assert mats.ndim == 3
    assert mats.shape[0] == len(subjects)
    assert mats.shape[1] == mats.shape[2] == len(labels)
    assert np.isfinite(mats).all()

    for i in range(mats.shape[0]):
        m = mats[i]
        assert float(np.max(np.abs(m - m.T))) <= 1e-5
        diag = np.diag(m)
        assert np.all(np.abs(diag - 1.0) <= 1e-3)

    _, rows = _read_csv(OUTPUT_DIR / "dmn_summary.csv")
    assert len(rows) == len(subjects)
    assert [r["subject_id"] for r in rows] == sorted(subjects)

    mat_by_subject = {sid: mats[idx] for idx, sid in enumerate(subjects)}
    for r in rows:
        sid = r["subject_id"]
        m = mat_by_subject[sid]
        triu = m[np.triu_indices(m.shape[0], k=1)]
        assert int(r["n_runs"]) >= 1
        assert int(r["n_timepoints"]) >= 20
        assert int(r["n_edges"]) == triu.size
        assert abs(float(r["mean_dmn_conn"]) - float(np.mean(triu))) <= 1e-5
        assert abs(float(r["std_dmn_conn"]) - float(np.std(triu))) <= 1e-5


def test_run_metadata_traceability():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))

    assert meta.get("task_id") == "OPENNEURO-CONN-002"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds001168"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"
    assert str(meta.get("snapshot_tag", "")).strip()

    assert int(meta.get("processing_subject_count", -1)) >= 1
    assert int(meta.get("processing_run_count", -1)) >= int(meta.get("processing_subject_count", -1))
    assert int(meta.get("input_file_count", -1)) >= int(meta.get("processing_run_count", -1))
    assert int(meta.get("input_bytes_total", -1)) > 0
    assert int(meta.get("records_count", -1)) == 3
    assert int(meta.get("bytes_total", -1)) > 0

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha
