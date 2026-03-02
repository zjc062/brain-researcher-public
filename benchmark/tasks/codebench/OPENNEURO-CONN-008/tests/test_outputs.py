import csv
import hashlib
import json
import os
from pathlib import Path

import nibabel as nib
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


def _subjects_from_dir(d: Path, suffix: str):
    out = set()
    for p in sorted(d.glob(f"*{suffix}")):
        sid = p.name.rsplit(suffix, 1)[0]
        if sid:
            out.add(sid)
    return out


def test_required_outputs_exist():
    for name in ["alff_maps", "falff_maps", "map_manifest.csv", "input_manifest.csv", "run_metadata.json"]:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"


def test_manifest_subject_consistency_and_map_files():
    m_fields, m_rows = _read_csv(OUTPUT_DIR / "map_manifest.csv")
    for col in [
        "subject_id",
        "session",
        "run_id",
        "alff_file",
        "falff_file",
        "alff_mean",
        "falff_mean",
        "n_timepoints",
        "tr",
        "frequency_band",
        "snapshot_tag",
        "method",
    ]:
        assert col in m_fields

    assert m_rows

    alff_subjects = _subjects_from_dir(OUTPUT_DIR / "alff_maps", "_alff.nii.gz")
    falff_subjects = _subjects_from_dir(OUTPUT_DIR / "falff_maps", "_falff.nii.gz")
    manifest_subjects = {r["subject_id"] for r in m_rows}

    assert alff_subjects == falff_subjects == manifest_subjects

    for r in m_rows:
        sid = r["subject_id"]
        assert sid.startswith("sub-")
        assert (OUTPUT_DIR / "alff_maps" / r["alff_file"]).exists()
        assert (OUTPUT_DIR / "falff_maps" / r["falff_file"]).exists()
        assert int(r["n_timepoints"]) >= 20
        assert float(r["tr"]) > 0.0
        assert r["frequency_band"] == "[0.01, 0.1]"
        assert r["method"] == "voxelwise_fft_alff_falff"

        alff_data = np.asarray(nib.load(str(OUTPUT_DIR / "alff_maps" / r["alff_file"])).get_fdata(), dtype=float)
        falff_data = np.asarray(nib.load(str(OUTPUT_DIR / "falff_maps" / r["falff_file"])).get_fdata(), dtype=float)
        assert alff_data.ndim == 3
        assert falff_data.ndim == 3
        assert np.isfinite(alff_data).all()
        assert np.isfinite(falff_data).all()
        assert float(np.std(alff_data)) > 1e-8
        assert float(np.std(falff_data)) > 1e-8
        assert abs(float(r["alff_mean"]) - float(np.mean(alff_data))) <= 1e-4
        assert abs(float(r["falff_mean"]) - float(np.mean(falff_data))) <= 1e-4


def test_input_manifest_and_metadata_traceability():
    i_fields, i_rows = _read_csv(OUTPUT_DIR / "input_manifest.csv")
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
        assert col in i_fields

    assert i_rows
    for r in i_rows:
        assert r["dataset_id"] == "ds001168"
        assert r["subject_id"].startswith("sub-")
        assert int(r["bytes"]) > 0
        s = r["sha256"].strip().lower()
        assert len(s) == 64
        int(s, 16)

    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta.get("task_id") == "OPENNEURO-CONN-008"
    assert meta.get("dataset_source") == "OpenNeuro"
    assert meta.get("dataset_id") == "ds001168"
    assert meta.get("status") == "ok"
    assert meta.get("reason") == "computed"
    assert meta.get("frequency_band") == [0.01, 0.1]

    assert int(meta.get("processing_subject_count", -1)) == len({r["subject_id"] for r in i_rows})
    assert int(meta.get("processing_run_count", -1)) == int(meta.get("processing_subject_count", -1))
    assert int(meta.get("input_file_count", -1)) == len(i_rows)
    assert int(meta.get("input_bytes_total", -1)) == sum(int(r["bytes"]) for r in i_rows)
    assert int(meta.get("records_count", -1)) == 4
    assert int(meta.get("bytes_total", -1)) > 0

    manifest_sha = _sha256_file(OUTPUT_DIR / "input_manifest.csv")
    assert meta.get("hash_manifest_sha256") == manifest_sha
