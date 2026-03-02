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


def _parse_kv(path: Path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def test_required_outputs_exist():
    for name in [
        "nbs_results.txt",
        "altered_edges.csv",
        "group_connectivity_stats.csv",
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
        assert row["dataset_id"] == "ds002424"
        assert row["snapshot_tag"].strip()
        assert row["subject_id"].startswith("sub-")
        assert int(row["bytes"]) > 0
        s = row["sha256"].strip().lower()
        assert len(s) == 64
        int(s, 16)


def test_group_stats_and_altered_edges_consistency():
    fieldnames, rows = _read_csv(OUTPUT_DIR / "group_connectivity_stats.csv")
    for col in [
        "roi_1",
        "roi_2",
        "t_stat",
        "p_uncorrected",
        "p_corrected",
        "adhd_mean",
        "control_mean",
        "n_adhd",
        "n_control",
        "significant",
    ]:
        assert col in fieldnames

    assert rows
    seen = set()
    sig_keys = set()
    for r in rows:
        key = tuple(sorted((r["roi_1"], r["roi_2"])))
        assert key not in seen
        seen.add(key)

        t = float(r["t_stat"])
        p_unc = float(r["p_uncorrected"])
        p_cor = float(r["p_corrected"])
        adhd_m = float(r["adhd_mean"])
        ctrl_m = float(r["control_mean"])

        assert -20.0 <= t <= 20.0
        assert 0.0 <= p_unc <= 1.0
        assert 0.0 <= p_cor <= 1.0
        assert -1.0 <= adhd_m <= 1.0
        assert -1.0 <= ctrl_m <= 1.0
        assert int(r["n_adhd"]) > 0
        assert int(r["n_control"]) > 0
        assert r["significant"] in {"0", "1"}
        if r["significant"] == "1":
            sig_keys.add(key)
            assert abs(t) >= 3.0
            assert p_cor < 0.05

    afields, altered = _read_csv(OUTPUT_DIR / "altered_edges.csv")
    for col in ["roi_1", "roi_2", "t_stat", "p_val", "adhd_mean", "control_mean", "n_adhd", "n_control"]:
        assert col in afields

    altered_keys = set()
    for r in altered:
        key = tuple(sorted((r["roi_1"], r["roi_2"])))
        altered_keys.add(key)
        assert key in sig_keys
        assert abs(float(r["t_stat"])) >= 3.0
        assert 0.0 <= float(r["p_val"]) < 0.05

    assert altered_keys == sig_keys


def test_summary_and_metadata_alignment():
    summary = _parse_kv(OUTPUT_DIR / "nbs_results.txt")
    _, rows = _read_csv(OUTPUT_DIR / "group_connectivity_stats.csv")
    _, altered = _read_csv(OUTPUT_DIR / "altered_edges.csv")
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))

    assert summary.get("dataset_id") == "ds002424"
    assert summary.get("method") == "voxelwise_msdl_nbs_proxy"
    assert summary.get("status") == "ok"
    assert summary.get("reason") == "computed"

    assert int(summary.get("subjects_used", "-1")) == int(meta.get("subjects_used", -2))
    assert int(summary.get("adhd_subjects", "-1")) == int(meta.get("adhd_subjects", -2))
    assert int(summary.get("control_subjects", "-1")) == int(meta.get("control_subjects", -2))
    assert float(summary.get("cluster_forming_t", "0")) == float(meta.get("cluster_forming_t", -1.0))
    assert int(summary.get("permutations", "0")) == int(meta.get("permutations", -1))
    assert int(summary.get("significant_edges", "-1")) == len(altered)

    assert meta.get("task_id") == "OPENNEURO-CONN-003"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds002424"
    assert meta.get("status") == "ok"
    assert int(meta.get("processing_subject_count", -1)) >= 2
    assert int(meta.get("processing_run_count", -1)) >= int(meta.get("processing_subject_count", -1))
    assert int(meta.get("input_file_count", -1)) >= int(meta.get("processing_run_count", -1))
    assert int(meta.get("records_count", -1)) == 4
    assert int(meta.get("bytes_total", -1)) > 0

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha
