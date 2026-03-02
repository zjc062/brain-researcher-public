import csv
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


OPENNEURO_GRAPHQL = "https://openneuro.org/crn/graphql"
DATASET_ID = "ds000030"
TASK_ID = "DATA-007"
SEED = 42


def _graphql(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        OPENNEURO_GRAPHQL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise RuntimeError(str(payload["errors"]))
    return payload["data"]


def _normalize_subject_id(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    return value if value.startswith("sub-") else f"sub-{value}"


def _normalize_sex(raw: str):
    value = str(raw or "").strip().lower()
    if value in {"m", "male", "man"}:
        return "M"
    if value in {"f", "female", "woman"}:
        return "F"
    return None


def _age_bin(age: float) -> str:
    lo = int(age // 10) * 10
    hi = lo + 9
    return f"{lo:02d}-{hi:02d}"


def _find_subject_dirs(files: list[dict]) -> set[str]:
    out = set()
    for item in files:
        filename = str(item.get("filename") or "")
        m = re.match(r"^(sub-[A-Za-z0-9][A-Za-z0-9_-]*)($|/)", filename)
        if m:
            out.add(m.group(1))
    return out


def _download_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _pick_column(fieldnames: list[str], candidates: list[str]) -> str:
    lookup = {f.lower(): f for f in fieldnames}
    for name in candidates:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return ""


def _parse_participants(tsv_text: str) -> tuple[list[dict], str]:
    lines = [line for line in tsv_text.splitlines() if line.strip()]
    if not lines:
        return [], "participants_tsv_empty"

    reader = csv.DictReader(lines, delimiter="\t")
    if not reader.fieldnames:
        return [], "participants_header_missing"

    participant_col = _pick_column(reader.fieldnames, ["participant_id", "subject_id", "sub_id"])
    age_col = _pick_column(reader.fieldnames, ["age"])
    sex_col = _pick_column(reader.fieldnames, ["sex", "gender"])

    if not participant_col:
        return [], "participants_missing_subject_column"
    if not age_col or not sex_col:
        return [], "participants_missing_age_or_sex_column"

    subjects = {}
    for row in reader:
        subject_id = _normalize_subject_id(row.get(participant_col, ""))
        if not subject_id:
            continue

        try:
            age = float(str(row.get(age_col, "")).strip())
        except ValueError:
            continue
        if not (0.0 <= age <= 120.0):
            continue

        sex = _normalize_sex(row.get(sex_col, ""))
        if sex is None:
            continue

        subjects[subject_id] = {"subject_id": subject_id, "age": age, "sex": sex}

    if not subjects:
        return [], "no_valid_subject_rows"
    return [subjects[sid] for sid in sorted(subjects)], "ok"


def _target_counts(n: int) -> tuple[int, int, int]:
    raw = [0.8 * n, 0.1 * n, 0.1 * n]
    base = [int(x) for x in raw]
    remaining = n - sum(base)
    remainders = [(raw[i] - base[i], -i, i) for i in range(3)]
    remainders.sort(reverse=True)
    for _, _, idx in remainders[:remaining]:
        base[idx] += 1
    return base[0], base[1], base[2]


def _stratified_split(records: list[dict], seed: int) -> tuple[list[str], list[str], list[str]]:
    by_stratum = defaultdict(list)
    for record in records:
        stratum = f"{record['sex']}|{_age_bin(record['age'])}"
        by_stratum[stratum].append(record["subject_id"])

    def _rank(subject_id: str, salt: str) -> str:
        return hashlib.sha256(f"{seed}|{salt}|{subject_id}".encode("utf-8")).hexdigest()

    train, val, test = [], [], []
    for stratum in sorted(by_stratum):
        ids = sorted(by_stratum[stratum], key=lambda sid: _rank(sid, f"stratum:{stratum}"))

        n_train, n_val, n_test = _target_counts(len(ids))
        train.extend(ids[:n_train])
        val.extend(ids[n_train : n_train + n_val])
        test.extend(ids[n_train + n_val : n_train + n_val + n_test])

    train.sort(key=lambda sid: _rank(sid, "train"))
    val.sort(key=lambda sid: _rank(sid, "val"))
    test.sort(key=lambda sid: _rank(sid, "test"))
    return train, val, test


def _write_split(path: Path, subjects: list[str], status: str, reason: str) -> None:
    if status == "ok":
        body = "\n".join(subjects) + "\n"
    else:
        body = "FAILED_PRECONDITION\n" f"reason={reason}\n"
    path.write_text(body, encoding="utf-8")


def main() -> None:
    output_dir = Path(os.environ.get("OUTPUT_DIR", "/app/output")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_meta = {
        "task_id": TASK_ID,
        "dataset_source": "OpenNeuro",
        "dataset_id": DATASET_ID,
        "status": "failed_precondition",
        "reason": "not_started",
        "seed": SEED,
        "snapshot_tag": "",
        "n_subjects_total": 0,
        "n_train": 0,
        "n_val": 0,
        "n_test": 0,
        "subject_dir_count": 0,
        "participants_row_count": 0,
        "used_subject_ids": [],
        "sex_counts": {},
        "age_bin_counts": {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    split_files = {
        "train": output_dir / "train_subjects.txt",
        "val": output_dir / "val_subjects.txt",
        "test": output_dir / "test_subjects.txt",
    }

    try:
        data = _graphql(
            """
            query GetDataset($id: ID!) {
              dataset(id: $id) {
                latestSnapshot {
                  tag
                  files {
                    filename
                    urls
                  }
                }
              }
            }
            """,
            {"id": DATASET_ID},
        )
        dataset = data.get("dataset") or {}
        latest = dataset.get("latestSnapshot") or {}
        files = latest.get("files") or []
        run_meta["snapshot_tag"] = str(latest.get("tag") or "")

        participants_entry = None
        for item in files:
            name = str(item.get("filename") or "")
            if name == "participants.tsv" or name.endswith("/participants.tsv"):
                participants_entry = item
                break
        if participants_entry is None:
            raise RuntimeError("participants_tsv_missing")

        urls = participants_entry.get("urls") or []
        if not urls:
            raise RuntimeError("participants_tsv_url_missing")

        tsv_text = _download_text(str(urls[0]))
        participants, parse_status = _parse_participants(tsv_text)
        if parse_status != "ok":
            raise RuntimeError(parse_status)
        run_meta["participants_row_count"] = len(participants)

        subject_dirs = _find_subject_dirs(files)
        run_meta["subject_dir_count"] = len(subject_dirs)
        if subject_dirs:
            keep = sorted({rec["subject_id"] for rec in participants} & subject_dirs)
            used = [rec for rec in participants if rec["subject_id"] in keep]
        else:
            used = participants

        if not used:
            raise RuntimeError("no_subjects_after_subject_dir_intersection")

        run_meta["used_subject_ids"] = [rec["subject_id"] for rec in used]
        run_meta["n_subjects_total"] = len(used)
        run_meta["sex_counts"] = dict(Counter(rec["sex"] for rec in used))
        run_meta["age_bin_counts"] = dict(Counter(_age_bin(rec["age"]) for rec in used))

        feasibility_reasons = []
        if len(used) < 10:
            feasibility_reasons.append("insufficient_subjects_for_80_10_10")
        if len(run_meta["sex_counts"]) < 2:
            feasibility_reasons.append("insufficient_sex_diversity_for_stratification")
        if len(run_meta["age_bin_counts"]) < 2:
            feasibility_reasons.append("insufficient_age_bin_diversity_for_stratification")

        strata_counts = Counter((rec["sex"], _age_bin(rec["age"])) for rec in used)
        dense_strata = sum(1 for count in strata_counts.values() if count >= 2)
        if dense_strata < 2:
            feasibility_reasons.append("strata_too_sparse_for_stable_stratification")

        if feasibility_reasons:
            run_meta["status"] = "failed_precondition"
            run_meta["reason"] = ";".join(feasibility_reasons)
            for key, path in split_files.items():
                _write_split(path, [], run_meta["status"], run_meta["reason"])
        else:
            train, val, test = _stratified_split(used, SEED)
            if not train or not val or not test:
                run_meta["status"] = "failed_precondition"
                run_meta["reason"] = "empty_split_after_allocation"
                for key, path in split_files.items():
                    _write_split(path, [], run_meta["status"], run_meta["reason"])
            else:
                overlap = (set(train) & set(val)) | (set(train) & set(test)) | (set(val) & set(test))
                merged = set(train) | set(val) | set(test)
                if overlap or len(merged) != len(used):
                    run_meta["status"] = "failed_precondition"
                    run_meta["reason"] = "split_integrity_check_failed"
                    for key, path in split_files.items():
                        _write_split(path, [], run_meta["status"], run_meta["reason"])
                else:
                    run_meta["status"] = "ok"
                    run_meta["reason"] = "split_generated"
                    run_meta["n_train"] = len(train)
                    run_meta["n_val"] = len(val)
                    run_meta["n_test"] = len(test)

                    for key, path in split_files.items():
                        if key == "train":
                            _write_split(path, train, run_meta["status"], run_meta["reason"])
                        elif key == "val":
                            _write_split(path, val, run_meta["status"], run_meta["reason"])
                        else:
                            _write_split(path, test, run_meta["status"], run_meta["reason"])

    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        run_meta["status"] = "failed_precondition"
        run_meta["reason"] = f"openneuro_network_error:{type(exc).__name__}"
        for _, path in split_files.items():
            _write_split(path, [], run_meta["status"], run_meta["reason"])
    except Exception as exc:
        run_meta["status"] = "failed_precondition"
        run_meta["reason"] = str(exc) or type(exc).__name__
        for _, path in split_files.items():
            _write_split(path, [], run_meta["status"], run_meta["reason"])

    (output_dir / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")
    print(f"status={run_meta['status']} reason={run_meta['reason']}")


if __name__ == "__main__":
    main()
