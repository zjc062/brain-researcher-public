"""
Use this file to define pytest tests that verify the outputs of the task.

This file will be copied to /tests/test_outputs.py and run by the /tests/test.sh file
from the working directory.
"""

import csv
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path


OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
DATASET_ID = "ds000105"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"


def _post_graphql(query: str) -> dict:
    payload = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "brain_researcher_benchmark",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
    data = json.loads(body)
    if data.get("errors"):
        raise AssertionError(f"OpenNeuro GraphQL error: {data['errors']}")
    return data


def _expected_subject_ids_from_openneuro() -> list[str]:
    query = f"""
query {{
  dataset(id: "{DATASET_ID}") {{
    latestSnapshot {{
      files {{
        filename
      }}
    }}
  }}
}}
"""
    try:
        data = _post_graphql(query)
        dataset = data.get("data", {}).get("dataset")
        if not dataset or not dataset.get("latestSnapshot"):
            raise AssertionError(f"OpenNeuro dataset not found: {DATASET_ID}")
        files = [
            f.get("filename")
            for f in dataset["latestSnapshot"].get("files", [])
            if isinstance(f.get("filename"), str)
        ]
        return _subject_ids_from_filenames(files)
    except (urllib.error.URLError, TimeoutError):
        return _expected_subject_ids_from_output_snapshot()


def _subject_ids_from_filenames(files: list[str]) -> list[str]:
    subject_ids = set()
    for filename in files:
        root = filename.split("/", 1)[0]
        if re.fullmatch(r"sub-[A-Za-z0-9]+", root):
            subject_ids.add(root)
    expected = sorted(subject_ids)
    if not expected:
        raise AssertionError("No subject IDs discovered from OpenNeuro snapshot files")
    return expected


def _expected_subject_ids_from_output_snapshot() -> list[str]:
    snapshot_path = OUTPUT_DIR / "openneuro_snapshot_files.json"
    assert snapshot_path.exists(), (
        "OpenNeuro API is unreachable and output fallback "
        f"{snapshot_path.name} is missing"
    )
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert str(data.get("dataset_id", "")).strip() == DATASET_ID
    files = data.get("files")
    assert isinstance(files, list) and files
    return _subject_ids_from_filenames([str(x) for x in files])


def _output_participant_ids() -> list[str]:
    path = OUTPUT_DIR / "participants.tsv"
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        assert reader.fieldnames is not None
        assert "participant_id" in reader.fieldnames
        rows = list(reader)

    assert len(rows) > 0
    participant_ids = [r["participant_id"] for r in rows]
    assert all(isinstance(pid, str) and pid for pid in participant_ids)
    assert all(re.fullmatch(r"sub-[A-Za-z0-9]+", pid) for pid in participant_ids)
    assert len(participant_ids) == len(set(participant_ids))
    assert participant_ids == sorted(participant_ids)
    return participant_ids


def test_required_files_exist():
    assert (OUTPUT_DIR / "dataset_description.json").exists()
    assert (OUTPUT_DIR / "participants.tsv").exists()


def test_dataset_description_schema():
    path = OUTPUT_DIR / "dataset_description.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "Name" in data
    assert "BIDSVersion" in data
    assert isinstance(data["Name"], str) and data["Name"].strip()
    assert isinstance(data["BIDSVersion"], str) and data["BIDSVersion"].strip()
    assert "DatasetDOI" in data
    assert isinstance(data["DatasetDOI"], str) and data["DatasetDOI"].strip()
    assert f"openneuro.{DATASET_ID}" in data["DatasetDOI"].lower()


def test_participants_tsv_schema_and_values():
    _output_participant_ids()


def test_participants_match_openneuro_snapshot_subjects():
    actual = _output_participant_ids()
    expected = _expected_subject_ids_from_openneuro()
    assert actual == expected

# --- Semantic Contract v1 ---
def _is_missing_value(v):
    if v is None:
        return True
    s = str(v).strip().lower()
    return s in {"", "na", "n/a", "nan", "none", "null"}


def _looks_numeric_column(col: str) -> bool:
    c = col.lower()

    # String-typed semantic labels should never be parsed as numeric.
    if c.endswith(("_name", "_label", "_type", "_id")):
        return False
    if any(tag in c for tag in ["name", "label", "type"]):
        return False

    # Explicitly non-numeric bookkeeping fields.
    if c in {"dataset_source", "dataset_id", "task_id", "method", "status", "reason", "source"}:
        return False

    keyword_hits = [
        "mean", "std", "variance", "var", "score", "accuracy", "auc", "f1",
        "precision", "recall", "sensitivity", "specificity", "mae", "mse", "rmse",
        "icc", "corr", "correlation", "beta", "coef", "effect", "age", "count",
        "subjects", "fold", "rank", "weight", "snr", "cnr", "qi1", "volume",
        "thickness", "motion",
    ]
    if any(k in c for k in keyword_hits):
        return True

    if c.startswith(("p_", "t_", "z_", "r_", "n_")):
        return True

    if c.endswith((
        "_p", "_t", "_z", "_r", "_count", "_mean", "_std", "_var",
        "_mae", "_mse", "_rmse", "_age", "_icc", "_auc", "_f1",
    )):
        return True

    return False

def _column_range(col: str):
    c = col.lower()
    if c == "age" or c.endswith("_age") or "actual_age" in c or "predicted_age" in c:
        return 0.0, 120.0
    if "p_value" in c or c.startswith("p_") or c.endswith("_p"):
        return 0.0, 1.0
    if any(k in c for k in ["accuracy", "chance", "auc", "f1", "precision", "recall", "icc"]):
        return 0.0, 1.0
    if "correlation" in c or c.endswith("_r") or c.startswith("r_"):
        return -1.0, 1.0
    if any(k in c for k in ["std", "variance", "count", "subjects", "fold", "rank", "mae", "mse", "rmse"]):
        return 0.0, None
    return None


def _safe_float(v):
    return float(str(v))


def _table_infos():
    infos = []
    for csv_path in OUTPUT_DIR.rglob("*.csv"):
        try:
            fieldnames, rows = read_table(csv_path, ",")
            infos.append((csv_path, fieldnames, rows))
        except Exception:
            continue
    for tsv_path in OUTPUT_DIR.rglob("*.tsv"):
        try:
            fieldnames, rows = read_table(tsv_path, "\t")
            infos.append((tsv_path, fieldnames, rows))
        except Exception:
            continue
    return infos


def _find_status_values(table_infos):
    vals = set()
    for _, fields, rows in table_infos:
        if "status" in fields:
            for r in rows:
                v = (r.get("status") or "").strip().lower()
                if v:
                    vals.add(v)
    for j in OUTPUT_DIR.rglob("*.json"):
        try:
            data = load_json(j)
        except Exception:
            continue
        if isinstance(data, dict):
            v = str(data.get("status", "")).strip().lower()
            if v:
                vals.add(v)
    return vals


def _subject_set(fields, rows):
    candidates = ["subject_id", "participant_id", "sub_id", "subject", "participant"]
    for c in candidates:
        if c in fields:
            out = {str(r.get(c)).strip() for r in rows if not _is_missing_value(r.get(c))}
            return out
    return set()


def test_semantic_integrity_contract():
    table_infos = _table_infos()
    status_values = _find_status_values(table_infos)
    is_failfast = any(v.startswith("failed") for v in status_values)

    # 1) Required columns should not be entirely empty unless explicit fail-fast.
    for name, spec in globals().get("OUTPUT_SCHEMA", {}).items():
        if not isinstance(spec, dict):
            continue
        p = OUTPUT_DIR / name.rstrip("/")
        if not p.exists() or p.is_dir():
            continue

        if p.suffix in {".csv", ".tsv"}:
            delim = "," if p.suffix == ".csv" else "\t"
            fields, rows = read_table(p, delim)
            for col in spec.get("required_columns", []):
                if col not in fields:
                    continue
                non_missing = [r.get(col) for r in rows if not _is_missing_value(r.get(col))]
                if is_failfast and col not in {"status", "reason", "subject_id", "participant_id", "stimulus_id", "connection_id"}:
                    continue
                assert non_missing, f"Column {col!r} in {p} is entirely missing/NA"

    # 2) Numeric-looking columns must parse as float and satisfy basic plausibility ranges.
    for p, fields, rows in table_infos:
        for col in fields:
            if not _looks_numeric_column(col):
                continue
            rng = _column_range(col)
            for r in rows:
                v = r.get(col)
                if _is_missing_value(v):
                    continue
                try:
                    fv = _safe_float(v)
                except Exception:
                    raise AssertionError(f"Non-numeric value in numeric-like column {col!r} for {p}: {v!r}")
                if rng is not None:
                    lo, hi = rng
                    if lo is not None:
                        assert fv >= lo - 1e-9, f"Value below range in {p} col={col}: {fv} < {lo}"
                    if hi is not None:
                        assert fv <= hi + 1e-9, f"Value above range in {p} col={col}: {fv} > {hi}"

    # 3) Cross-file subject-set consistency when multiple subject tables exist.
    subject_sets = []
    for _, fields, rows in table_infos:
        s = _subject_set(fields, rows)
        if s:
            subject_sets.append(s)

    if len(subject_sets) >= 2:
        base = subject_sets[0]
        for s in subject_sets[1:]:
            if is_failfast and (len(base) <= 1 or len(s) <= 1):
                continue
            assert s == base, "Subject/participant sets are inconsistent across output tables"

    # 4) Input traceability via run_metadata when present.
    run_meta = OUTPUT_DIR / "run_metadata.json"
    if run_meta.exists():
        data = load_json(run_meta)
        assert isinstance(data, dict), "run_metadata.json must be a JSON object"
        for k in ["task_id", "dataset_source", "dataset_id", "status", "reason", "records_count", "bytes_total"]:
            assert k in data, f"run_metadata.json missing key: {k}"

        st = str(data.get("status", "")).strip().lower()
        assert st in {"ok", "failed_precondition"}, f"Unexpected run_metadata status: {st}"

        rc = int(data.get("records_count", 0))
        bt = int(data.get("bytes_total", 0))
        assert rc >= 0
        assert bt >= 0
        if st == "ok":
            assert rc >= 1, "status=ok but records_count<1"
            assert str(data.get("reason", "")).strip() not in {"", "missing_input_dir", "input_dir_empty"}
        else:
            assert str(data.get("reason", "")).strip() not in {"", "preconditions_met"}



# --- Semantic Contract v2 (Generic Mapping) ---
def _sc2_parse_task_metadata() -> dict:
    import re

    task_dir = Path(__file__).resolve().parents[1]
    task_toml = task_dir / "task.toml"
    text = task_toml.read_text(encoding="utf-8") if task_toml.exists() else ""

    def _pull(key: str) -> str:
        m = re.search(rf'^\s*{re.escape(key)}\s*=\s*"([^\"]*)"', text, flags=re.M)
        return m.group(1).strip() if m else ""

    dataset_id = _pull("dataset_id") or str(globals().get("DATASET_ID", "")).strip()
    dataset_source = _pull("dataset_source")
    if not dataset_source and dataset_id.startswith("ds"):
        dataset_source = "OpenNeuro"

    return {
        "task_id": _pull("task_id") or task_dir.name,
        "dataset_source": dataset_source,
        "dataset_id": dataset_id,
    }


def _sc2_scan_input(dataset_id: str) -> dict:
    import os as _os

    candidates = []
    env_input = _os.environ.get("INPUT_DIR", "").strip()
    if env_input:
        candidates.append(Path(env_input))
    if dataset_id:
        candidates.append(Path("/task/cache") / dataset_id)
    candidates.extend([Path("/task/input"), Path("/app/input")])

    uniq = []
    seen = set()
    for c in candidates:
        try:
            rc = c.resolve()
        except Exception:
            rc = c
        key = str(rc)
        if key in seen:
            continue
        seen.add(key)
        if c.exists() and c.is_dir():
            uniq.append(c)

    file_count = 0
    byte_count = 0
    subjects = set()
    for root in uniq:
        for dirpath, _, filenames in _os.walk(root):
            for fn in filenames:
                p = Path(dirpath) / fn
                try:
                    st = p.stat()
                except Exception:
                    continue
                file_count += 1
                byte_count += int(st.st_size)
                rel = str(p)
                for sid in re.findall(r"sub-[A-Za-z0-9]+", rel):
                    subjects.add(sid)

    return {
        "input_scanned_records_count": file_count,
        "input_scanned_bytes_total": byte_count,
        "input_scanned_subject_ids": sorted(subjects),
        "input_scanned_subject_count": len(subjects),
    }


def _sc2_fetch_openneuro_snapshot(dataset_id: str) -> dict:
    import json as _json
    import urllib.request as _urlreq

    if not dataset_id:
        return {
            "input_openneuro_snapshot_tag": "",
            "input_openneuro_snapshot_subject_ids": [],
            "input_openneuro_snapshot_subject_count": 0,
        }

    graphql_url = str(globals().get("GRAPHQL_URL", "https://openneuro.org/crn/graphql"))
    query = f"""
query {{
  dataset(id: "{dataset_id}") {{
    latestSnapshot {{
      tag
      files {{
        filename
      }}
    }}
  }}
}}
"""
    payload = _json.dumps({"query": query}).encode("utf-8")
    req = _urlreq.Request(
        graphql_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "brain_researcher_benchmark",
        },
        method="POST",
    )

    try:
        with _urlreq.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
        data = _json.loads(body)
        if data.get("errors"):
            raise RuntimeError(str(data["errors"]))
        dataset = data.get("data", {}).get("dataset")
        if not dataset or not dataset.get("latestSnapshot"):
            raise RuntimeError("snapshot_missing")

        snap = dataset["latestSnapshot"]
        tag = str(snap.get("tag", "")).strip()
        subjects = sorted(
            {
                fn.split("/", 1)[0]
                for fn in [
                    f["filename"]
                    for f in snap.get("files", [])
                    if isinstance(f.get("filename"), str)
                ]
                if re.fullmatch(r"sub-[A-Za-z0-9]+", fn.split("/", 1)[0])
            }
        )
        return {
            "input_openneuro_snapshot_tag": tag,
            "input_openneuro_snapshot_subject_ids": subjects,
            "input_openneuro_snapshot_subject_count": len(subjects),
        }
    except Exception:
        return {
            "input_openneuro_snapshot_tag": "",
            "input_openneuro_snapshot_subject_ids": [],
            "input_openneuro_snapshot_subject_count": 0,
        }


def _sc2_is_missing(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        s = v.strip().lower()
        return s in {"", "na", "n/a", "nan", "none", "null"}
    if isinstance(v, (list, tuple, set, dict)):
        return len(v) == 0
    return False


def _sc2_read_table_rows(file_name: str) -> list[dict[str, str]]:
    import csv as _csv

    p = OUTPUT_DIR / file_name
    delim = "	" if p.suffix == ".tsv" else ","
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = _csv.DictReader(f, delimiter=delim)
        return list(reader)


def _sc2_json_get(data, field_path: str):
    cur = data
    for part in field_path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _sc2_output_value(spec: dict):
    import json as _json

    src = spec["source"]

    if src == "output_json_field_optional":
        p = OUTPUT_DIR / spec["file"]
        if not p.exists():
            return None
        try:
            data = _json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        v = _sc2_json_get(data, spec["field"])
        return None if v is None else str(v).strip()

    if src == "output_json_field_int_optional":
        p = OUTPUT_DIR / spec["file"]
        if not p.exists():
            return None
        try:
            data = _json.loads(p.read_text(encoding="utf-8"))
            v = _sc2_json_get(data, spec["field"])
            if v is None:
                return None
            return int(float(str(v).strip()))
        except Exception:
            return None

    if src == "output_json_field":
        p = OUTPUT_DIR / spec["file"]
        data = _json.loads(p.read_text(encoding="utf-8"))
        v = _sc2_json_get(data, spec["field"])
        return None if v is None else str(v).strip()

    if src == "output_json_field_int":
        p = OUTPUT_DIR / spec["file"]
        data = _json.loads(p.read_text(encoding="utf-8"))
        v = _sc2_json_get(data, spec["field"])
        return int(float(str(v).strip()))

    if src == "output_table_unique_sorted":
        rows = _sc2_read_table_rows(spec["file"])
        col = spec["column"]
        return sorted({str(r.get(col, "")).strip() for r in rows if str(r.get(col, "")).strip()})

    if src == "output_table_unique_count":
        rows = _sc2_read_table_rows(spec["file"])
        col = spec["column"]
        return len({str(r.get(col, "")).strip() for r in rows if str(r.get(col, "")).strip()})

    if src == "output_table_first":
        rows = _sc2_read_table_rows(spec["file"])
        assert rows, f"table has no rows: {spec['file']}"
        return str(rows[0].get(spec["column"], "")).strip()

    if src == "output_table_first_int":
        rows = _sc2_read_table_rows(spec["file"])
        assert rows, f"table has no rows: {spec['file']}"
        return int(float(str(rows[0].get(spec["column"], "0")).strip()))

    if src == "output_exists":
        return (OUTPUT_DIR / spec["path"]).exists()

    raise AssertionError(f"Unsupported output source: {src}")


def _sc2_resolve_operand(spec: dict, input_stats: dict):
    if "literal" in spec:
        return spec["literal"]

    src = spec.get("source", "")
    if src.startswith("input_"):
        if src.startswith("input_openneuro_") and src not in input_stats:
            input_stats.update(_sc2_fetch_openneuro_snapshot(input_stats.get("input_task_dataset_id", "")))
        return input_stats.get(src)

    return _sc2_output_value(spec)


def _sc2_eval_simple_op(op: str, left, right, check_id: str):
    if op == "eq":
        assert left == right, f"[{check_id}] eq failed: left={left!r} right={right!r}"
        return
    if op == "ne":
        assert left != right, f"[{check_id}] ne failed: left={left!r} right={right!r}"
        return
    if op == "contains":
        assert str(right) in str(left), f"[{check_id}] contains failed: left={left!r} right={right!r}"
        return
    if op == "ge":
        assert float(left) >= float(right), f"[{check_id}] ge failed: left={left!r} right={right!r}"
        return
    if op == "le":
        assert float(left) <= float(right), f"[{check_id}] le failed: left={left!r} right={right!r}"
        return
    if op == "gt":
        assert float(left) > float(right), f"[{check_id}] gt failed: left={left!r} right={right!r}"
        return
    if op == "lt":
        assert float(left) < float(right), f"[{check_id}] lt failed: left={left!r} right={right!r}"
        return
    if op == "subset":
        lset = set(left or [])
        rset = set(right or [])
        assert lset.issubset(rset), f"[{check_id}] subset failed: left_only={sorted(lset - rset)!r}"
        return
    raise AssertionError(f"[{check_id}] unsupported op: {op}")


def _sc2_check_when(check: dict, input_stats: dict) -> bool:
    cond = check.get("when")
    if not isinstance(cond, dict):
        return True
    l = _sc2_resolve_operand(cond["left"], input_stats)
    r = _sc2_resolve_operand(cond["right"], input_stats)
    _sc2_eval_simple_op(cond.get("op", "eq"), l, r, check.get("id", "(when)"))
    return True


def _sc2_eval_check(check: dict, input_stats: dict):
    cid = check.get("id", "(unnamed)")

    try:
        _sc2_check_when(check, input_stats)
    except AssertionError:
        return

    op = check.get("op", "eq")
    left = _sc2_resolve_operand(check["left"], input_stats)
    right = _sc2_resolve_operand(check["right"], input_stats)

    if op.endswith("_if_present"):
        base_op = op[: -len("_if_present")]
        if _sc2_is_missing(left) or _sc2_is_missing(right):
            return
        _sc2_eval_simple_op(base_op, left, right, cid)
        return

    _sc2_eval_simple_op(op, left, right, cid)


def test_semantic_contract_v2_generic_mapping():
    contract_path = Path(__file__).parent / "semantic_contract.json"
    assert contract_path.exists(), f"semantic contract missing: {contract_path}"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))

    checks = contract.get("checks")
    assert isinstance(checks, list) and checks, "semantic contract must contain checks"

    meta = _sc2_parse_task_metadata()
    input_stats = {
        "input_task_id": meta.get("task_id", ""),
        "input_task_dataset_source": meta.get("dataset_source", ""),
        "input_task_dataset_id": meta.get("dataset_id", ""),
    }
    input_stats.update(_sc2_scan_input(input_stats["input_task_dataset_id"]))

    for check in checks:
        assert isinstance(check, dict), "each semantic check must be object"
        assert "left" in check and "right" in check and "op" in check
        _sc2_eval_check(check, input_stats)
