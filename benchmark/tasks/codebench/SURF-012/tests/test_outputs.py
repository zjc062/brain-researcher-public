import csv
import hashlib
import json
import os
import pickle
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
TASK_DIR = Path(__file__).resolve().parents[1]

REQUIRED_OUTPUTS = json.loads('["lh_myelin.gii", "rh_myelin.gii", "myelin_plot.png", "input_manifest.csv", "run_metadata.json"]')
OUTPUT_SCHEMA = json.loads('{"lh_myelin.gii": {"type": "gii"}, "rh_myelin.gii": {"type": "gii"}, "myelin_plot.png": {"type": "png", "min_size_px": [64, 64]}, "input_manifest.csv": {"type": "csv", "required_columns": ["dataset_id", "source_path", "bytes", "sha256"]}, "run_metadata.json": {"type": "json", "required_keys": ["task_id", "dataset_source", "dataset_id", "status", "reason", "method", "n_input_files", "n_subjects", "records_count", "bytes_total", "hash_manifest_sha256"]}}')
METRIC_VALIDATION = {
    "n_input_files_min": {"min": 0},
    "n_subjects_min": {"min": 0},
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path, delimiter: str = ",") -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        assert reader.fieldnames is not None, f"Missing CSV header: {path}"
        rows = list(reader)
    return list(reader.fieldnames), rows


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_task_meta() -> dict:
    text = (TASK_DIR / "task.toml").read_text(encoding="utf-8")

    def pull(key: str) -> str:
        for line in text.splitlines():
            line = line.strip()
            if line.startswith(f"{key} = "):
                return line.split("=", 1)[1].strip().strip('"')
        return ""

    return {
        "task_id": pull("task_id"),
        "dataset_source": pull("dataset_source"),
        "dataset_id": pull("dataset_id"),
    }


def parse_output(path: Path, typ: str) -> None:
    if typ == "json":
        assert isinstance(load_json(path), dict)
        return
    if typ == "csv":
        read_csv(path, ",")
        return
    if typ == "tsv":
        read_csv(path, "	")
        return
    if typ == "npy":
        np.load(path)
        return
    if typ == "png":
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            w, h = img.size
            assert w >= 64 and h >= 64
        return
    if typ in {"nifti", "mgz"}:
        img = nib.load(str(path))
        data = np.asanyarray(img.dataobj)
        assert data.size > 0
        return
    if typ == "gii":
        img = nib.load(str(path))
        assert hasattr(img, "darrays") and len(img.darrays) > 0
        return
    if typ == "annot":
        from nibabel.freesurfer.io import read_annot
        labels, ctab, names = read_annot(str(path))
        assert labels.size > 0 and len(names) > 0
        return
    if typ == "curv":
        from nibabel.freesurfer.io import read_morph_data
        vals = read_morph_data(str(path))
        assert vals.size > 0
        return
    if typ == "pickle":
        with path.open("rb") as f:
            pickle.load(f)
        return
    if typ == "directory":
        assert path.is_dir()
        return
    assert path.stat().st_size > 0


def test_required_outputs_exist() -> None:
    for rel in REQUIRED_OUTPUTS:
        p = OUTPUT_DIR / rel.rstrip("/")
        if rel.endswith("/"):
            assert p.exists() and p.is_dir(), f"Missing required directory: {p}"
        else:
            assert p.exists() and p.is_file(), f"Missing required file: {p}"


def test_output_schema_constraints() -> None:
    for rel, spec in OUTPUT_SCHEMA.items():
        typ = spec.get("type", "file")
        p = OUTPUT_DIR / rel.rstrip("/")

        if typ == "directory":
            assert p.exists() and p.is_dir(), f"Missing directory output: {p}"
            min_files = int(spec.get("min_file_count", 0))
            if min_files > 0:
                actual = sum(1 for _ in p.iterdir())
                assert actual >= min_files
            continue

        assert p.exists() and p.is_file(), f"Missing schema output: {p}"
        parse_output(p, typ)

        if typ == "json":
            data = load_json(p)
            for key in spec.get("required_keys", []):
                assert key in data, f"Missing JSON key {key!r} in {p}"

        if typ in {"csv", "tsv"}:
            delim = "," if typ == "csv" else "	"
            fields, rows = read_csv(p, delim)
            for col in spec.get("required_columns", []):
                assert col in fields, f"Missing column {col!r} in {p}"
            if rows:
                for col in spec.get("required_columns", []):
                    non_empty = [r.get(col) for r in rows if str(r.get(col, "")).strip()]
                    assert non_empty, f"Column {col!r} empty in {p}"


def validate_manifest(allow_empty: bool) -> list[dict[str, str]]:
    _, rows = read_csv(OUTPUT_DIR / "input_manifest.csv", ",")
    if not allow_empty:
        assert rows, "input_manifest.csv should have rows on success"

    for row in rows:
        assert row["dataset_id"] == "t1w_t2w_images"
        src = Path(row["source_path"])
        assert src.exists() and src.is_file(), f"Manifest source missing: {src}"
        b = int(row["bytes"])
        assert b > 0 and src.stat().st_size == b
        digest = row["sha256"]
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
        assert sha256_file(src) == digest
    return rows


def test_task_semantics_and_status_branch() -> None:
    meta = load_json(OUTPUT_DIR / "run_metadata.json")
    assert meta["task_id"] == "SURF-012"
    assert meta["dataset_source"] == "Provided"
    assert meta["dataset_id"] == "t1w_t2w_images"

    status = str(meta.get("status", ""))
    assert status in {"ok", "failed_precondition"}
    assert str(meta.get("reason", "")).strip()

    assert int(meta.get("n_input_files", 0)) >= 0
    assert int(meta.get("n_subjects", 0)) >= 0
    assert int(meta.get("records_count", 0)) >= 0
    assert int(meta.get("bytes_total", 0)) >= 0

    if status == "ok":
        validate_manifest(allow_empty=False)
    else:
        validate_manifest(allow_empty=True)


def test_manifest_hash_traceability() -> None:
    meta = load_json(OUTPUT_DIR / "run_metadata.json")
    manifest = OUTPUT_DIR / "input_manifest.csv"
    expected_sha = sha256_file(manifest)
    actual_sha = str(meta.get("hash_manifest_sha256", "")).strip()
    assert actual_sha
    assert actual_sha == expected_sha


def test_metric_validation_contract() -> None:
    meta = load_json(OUTPUT_DIR / "run_metadata.json")
    assert int(meta.get("n_input_files", 0)) >= METRIC_VALIDATION["n_input_files_min"]["min"]
    assert int(meta.get("n_subjects", 0)) >= METRIC_VALIDATION["n_subjects_min"]["min"]


def is_missing(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, tuple, set, dict)):
        return len(v) == 0
    return False


def output_value(spec: dict):
    src = spec.get("source")
    if src == "output_json_field_optional":
        p = OUTPUT_DIR / spec["file"]
        if not p.exists():
            return None
        return load_json(p).get(spec["field"])
    if src == "output_json_field_int_optional":
        p = OUTPUT_DIR / spec["file"]
        if not p.exists():
            return None
        val = load_json(p).get(spec["field"])
        if val is None:
            return None
        return int(float(val))
    if src == "output_table_unique_sorted":
        p = OUTPUT_DIR / spec["file"]
        if not p.exists():
            return None
        _, rows = read_csv(p, ",")
        col = spec["column"]
        vals = sorted({str(r.get(col, "")).strip() for r in rows if str(r.get(col, "")).strip()})
        return vals
    raise AssertionError(f"Unsupported semantic source: {src}")


def resolve_operand(spec: dict, input_stats: dict):
    if "literal" in spec:
        return spec["literal"]
    src = spec.get("source", "")
    if src.startswith("input_"):
        return input_stats.get(src)
    return output_value(spec)


def eval_op(op: str, left, right, check_id: str) -> None:
    if op == "eq":
        assert left == right, f"[{check_id}] eq failed: {left!r} != {right!r}"
        return
    if op == "ne":
        assert left != right, f"[{check_id}] ne failed: {left!r} == {right!r}"
        return
    if op == "ge":
        assert float(left) >= float(right), f"[{check_id}] ge failed: {left!r} < {right!r}"
        return
    raise AssertionError(f"Unsupported semantic op: {op}")


def eval_check(check: dict, input_stats: dict) -> None:
    op = check.get("op", "eq")
    left = resolve_operand(check["left"], input_stats)
    right = resolve_operand(check["right"], input_stats)
    if op.endswith("_if_present"):
        base = op[: -len("_if_present")]
        if is_missing(left) or is_missing(right):
            return
        eval_op(base, left, right, check.get("id", "(unnamed)"))
        return
    eval_op(op, left, right, check.get("id", "(unnamed)"))


def test_semantic_contract_v2_generic_mapping() -> None:
    contract_path = TASK_DIR / "tests/semantic_contract.json"
    assert contract_path.exists()
    contract = load_json(contract_path)
    checks = contract.get("checks")
    assert isinstance(checks, list) and checks

    meta = parse_task_meta()
    input_stats = {
        "input_task_id": meta.get("task_id", ""),
        "input_task_dataset_source": meta.get("dataset_source", ""),
        "input_task_dataset_id": meta.get("dataset_id", ""),
    }

    for check in checks:
        assert isinstance(check, dict)
        assert "left" in check and "right" in check and "op" in check
        eval_check(check, input_stats)
