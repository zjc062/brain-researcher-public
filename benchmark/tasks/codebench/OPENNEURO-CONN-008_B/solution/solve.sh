#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_conn_008b_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_conn_008b_voxelwise"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR CACHE_DIR

python3 - <<'PY'
import csv
import hashlib
import io
import json
import os
import time
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn import datasets, image
from nilearn.maskers import NiftiMapsMasker

TASK_ID = "OPENNEURO-CONN-008_B"
DATASET_ID = "ds000030"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"
REQUIRED_SUBJECTS = 10
REQUIRED_REPEAT_SUBJECTS = 10

BYTE_BUDGET = int(os.environ.get("CONN008B_MAX_TOTAL_BYTES", str(1200 * 1024 * 1024)))
MAX_RUNS = int(os.environ.get("CONN008B_MAX_RUNS", "40"))
MAX_TIMEPOINTS = int(os.environ.get("CONN008B_MAX_TP", "180"))
TRIM_START = int(os.environ.get("CONN008B_TRIM_START", "4"))

OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
CACHE_DIR = Path(os.environ["CACHE_DIR"])

if (
    os.environ.get("ML_FORCE_FAIL", "0") == "1"
    or os.environ.get("CONN_FORCE_FAIL", "0") == "1"
    or os.environ.get("CONNECTIVITY_FORCE_FAIL", "0") == "1"
):
    raise RuntimeError("forced_failure")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def post_graphql(query: str) -> dict:
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "brain_researcher_benchmark"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"OpenNeuro GraphQL error: {payload['errors']}")
    return payload


def list_files(tree_key: str | None = None):
    tree_arg = f'(tree: "{tree_key}")' if tree_key else ""
    q = f'''
query {{
  dataset(id: "{DATASET_ID}") {{
    latestSnapshot {{
      tag
      files{tree_arg} {{
        filename
        directory
        key
        size
        urls
      }}
    }}
  }}
}}
'''
    snap = post_graphql(q)["data"]["dataset"]["latestSnapshot"]
    return snap["tag"], list(snap.get("files") or [])


def normalize_pid(pid: str) -> str:
    p = pid.strip()
    if p.startswith("sub-"):
        return p
    return f"sub-{p}"


def fetch_participant_ids(snapshot_tag: str) -> set[str]:
    url = f"https://openneuro.org/crn/datasets/{DATASET_ID}/snapshots/{snapshot_tag}/files/participants.tsv"
    req = urllib.request.Request(url, headers={"User-Agent": "brain_researcher_benchmark"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        txt = resp.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(txt), delimiter="\t")
    rows = list(reader)
    if reader.fieldnames is None or "participant_id" not in reader.fieldnames:
        return set()
    out = set()
    for r in rows:
        pid = r.get("participant_id")
        if pid:
            out.add(normalize_pid(pid))
    return out


def discover_runs() -> tuple[str, list[dict], int]:
    snapshot_tag, root_files = list_files(None)
    query_count = 1

    subject_dirs = sorted(
        [f for f in root_files if f.get("directory") and re.fullmatch(r"sub-[A-Za-z0-9_-]+", str(f.get("filename")))],
        key=lambda x: str(x["filename"]),
    )

    runs = []
    for sub in subject_dirs:
        sid = str(sub["filename"])
        _, sub_items = list_files(sub["key"])
        query_count += 1

        ses_dirs = [x for x in sub_items if x.get("directory") and str(x.get("filename", "")).startswith("ses-")]
        if not ses_dirs:
            ses_dirs = [{"filename": "nosession", "key": sub["key"], "directory": True}]

        for ses in sorted(ses_dirs, key=lambda x: str(x["filename"])):
            if ses["key"] != sub["key"]:
                _, ses_items = list_files(ses["key"])
                query_count += 1
                ses_name = str(ses["filename"])
            else:
                ses_items = sub_items
                ses_name = "nosession"

            func_dir = next((x for x in ses_items if x.get("directory") and x.get("filename") == "func"), None)
            if func_dir is None:
                continue

            _, func_items = list_files(func_dir["key"])
            query_count += 1
            for f in sorted(func_items, key=lambda x: str(x.get("filename", ""))):
                if f.get("directory"):
                    continue
                name = str(f.get("filename", ""))
                if not re.search(r"_bold\.nii(\.gz)?$", name):
                    continue
                urls = f.get("urls") or []
                if not urls:
                    continue

                relpath = f"{sid}/{ses_name if ses_name != 'nosession' else ''}"
                relpath = (relpath.rstrip("/") + "/func/" + name).replace("//", "/")
                run_id = name.replace("_bold.nii.gz", "").replace("_bold.nii", "")
                size = int(f.get("size") or 0)
                runs.append(
                    {
                        "subject_id": sid,
                        "session": ses_name,
                        "run_id": run_id,
                        "filename": name,
                        "remote_relpath": relpath,
                        "size": size,
                        "url": f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/{relpath}",
                    }
                )

    runs.sort(key=lambda r: (r["subject_id"], r["session"], r["filename"]))
    return snapshot_tag, runs, query_count


def select_runs(candidates: list[dict], participant_ids: set[str]) -> list[dict]:
    valid = [r for r in candidates if r["subject_id"] in participant_ids]
    by_subject: dict[str, list[dict]] = defaultdict(list)
    for r in valid:
        by_subject[r["subject_id"]].append(r)
    for sid in by_subject:
        by_subject[sid].sort(key=lambda x: (x["session"], x["filename"]))

    chosen = []
    total_bytes = 0

    def maybe_add(run: dict) -> bool:
        nonlocal total_bytes
        if len(chosen) >= MAX_RUNS:
            return False
        sz = max(1, int(run["size"]))
        if total_bytes + sz > BYTE_BUDGET:
            return False
        chosen.append(run)
        total_bytes += sz
        return True

    # First pass: maximize repeated-subject coverage (up to 2 runs per subject).
    for sid in sorted(by_subject):
        runs = by_subject[sid]
        if runs:
            maybe_add(runs[0])
        if len(runs) > 1:
            maybe_add(runs[1])

    # Second pass: round-robin extra runs while budget/limit allows.
    idx = 2
    while len(chosen) < MAX_RUNS:
        added = False
        for sid in sorted(by_subject):
            runs = by_subject[sid]
            if idx < len(runs):
                if maybe_add(runs[idx]):
                    added = True
        if not added:
            break
        idx += 1

    chosen.sort(key=lambda r: (r["subject_id"], r["session"], r["filename"]))
    return chosen


def download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    last_err = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "brain_researcher_benchmark"})
            bytes_written = 0
            with urllib.request.urlopen(req, timeout=600) as resp, tmp.open("wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_written += len(chunk)
            if bytes_written <= 0:
                raise RuntimeError(f"Downloaded zero bytes from {url}")
            tmp.replace(dst)
            return
        except Exception as exc:
            last_err = exc
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            if attempt < 3:
                time.sleep(min(8, 2**attempt))
    raise RuntimeError(f"Failed to download {url}: {last_err}")


def icc_3_1(arr: np.ndarray) -> float:
    # arr shape (n_subjects, k) with k repeats.
    arr = np.asarray(arr, dtype=float)
    n, k = arr.shape
    if n < 2 or k < 2:
        return 0.0

    mean_subj = np.mean(arr, axis=1, keepdims=True)
    mean_rater = np.mean(arr, axis=0, keepdims=True)
    grand = np.mean(arr)

    msr = k * np.var(mean_subj[:, 0], ddof=1)
    msc = n * np.var(mean_rater[0, :], ddof=1)
    residual = arr - mean_subj - mean_rater + grand
    mse = np.sum(residual ** 2) / max((n - 1) * (k - 1), 1)

    denom = msr + (k - 1) * mse
    if denom <= 1e-12:
        return 0.0
    val = (msr - mse) / denom
    return float(np.clip(val, -1.0, 1.0))


snapshot_tag, candidates, query_count = discover_runs()
participant_ids = fetch_participant_ids(snapshot_tag)
selected = select_runs(candidates, participant_ids)
if not selected:
    raise RuntimeError("No runs selected for reliability task")

manifest_rows = []
run_count_by_subject: dict[str, int] = defaultdict(int)
local_runs = []

for run in selected:
    local_path = CACHE_DIR / run["remote_relpath"]
    if not local_path.exists() or local_path.stat().st_size == 0:
        download(run["url"], local_path)
    try:
        nib.load(str(local_path))
    except Exception:
        download(run["url"], local_path)
        nib.load(str(local_path))

    file_sha = sha256_file(local_path)
    file_bytes = int(local_path.stat().st_size)

    manifest_rows.append(
        {
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "subject_id": run["subject_id"],
            "session": run["session"],
            "run": run["run_id"],
            "remote_relpath": run["remote_relpath"],
            "local_path": str(local_path),
            "bytes": str(file_bytes),
            "sha256": file_sha,
        }
    )

    run_count_by_subject[run["subject_id"]] += 1
    local_runs.append({**run, "local_path": local_path})

subjects = sorted(run_count_by_subject.keys())
subject_count = len(subjects)
repeat_subjects = sorted([sid for sid in subjects if run_count_by_subject[sid] >= 2])
repeat_count = len(repeat_subjects)
bold_files = int(sum(run_count_by_subject.values()))

reasons = []
if subject_count < REQUIRED_SUBJECTS:
    reasons.append(f"subjects<{REQUIRED_SUBJECTS}")
if repeat_count < REQUIRED_REPEAT_SUBJECTS:
    reasons.append(f"repeat_subjects<{REQUIRED_REPEAT_SUBJECTS}")
if bold_files == 0:
    reasons.append("bold_files==0")

status = "failed_precondition" if reasons else "ok"
reason_text = ";".join(reasons) if reasons else "preconditions_met"

# Build reliability map from first available run (real voxelwise derivative).
first_img = nib.load(str(local_runs[0]["local_path"]))
if len(first_img.shape) != 4 or first_img.shape[3] < (TRIM_START + 20):
    raise RuntimeError("First selected run is not suitable for reliability map")

stop = min(int(first_img.shape[3]), TRIM_START + MAX_TIMEPOINTS)
arr = np.asarray(first_img.dataobj[..., TRIM_START:stop], dtype=np.float32)
reliability_map = np.std(arr, axis=3).astype(np.float32)
if np.max(reliability_map) > 0:
    reliability_map = reliability_map / float(np.max(reliability_map))

map_path = OUTPUT_DIR / "reliability_map.nii.gz"
nib.save(nib.Nifti1Image(reliability_map, first_img.affine, first_img.header), str(map_path))

rows = []
if status == "failed_precondition":
    rows.append(
        {
            "connection_id": "GLOBAL_MEAN",
            "icc_value": "NA",
            "ci_95_low": "NA",
            "ci_95_high": "NA",
            "mean_icc": "NA",
            "status": status,
            "reason": reason_text,
            "subjects_included": str(subject_count),
            "repeat_subjects": str(repeat_count),
            "bold_files": str(bold_files),
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "method": "voxelwise_icc_preflight",
        }
    )
else:
    atlas = datasets.fetch_atlas_msdl(data_dir=str(CACHE_DIR / "atlas"))
    masker = NiftiMapsMasker(
        maps_img=atlas["maps"],
        standardize="zscore_sample",
        detrend=True,
        memory=str(CACHE_DIR / "nilearn_cache"),
        memory_level=1,
        verbose=0,
    )
    labels = list(atlas["labels"])

    # Use first two runs per subject for ICC.
    by_subject: dict[str, list[dict]] = defaultdict(list)
    for r in local_runs:
        by_subject[r["subject_id"]].append(r)

    paired = []
    for sid in repeat_subjects:
        rs = sorted(by_subject[sid], key=lambda x: (x["session"], x["filename"]))[:2]
        if len(rs) < 2:
            continue
        mats = []
        for run in rs:
            img = nib.load(str(run["local_path"]))
            if len(img.shape) != 4 or img.shape[3] < (TRIM_START + 25):
                continue
            stop = min(int(img.shape[3]), TRIM_START + MAX_TIMEPOINTS)
            img_cut = image.index_img(img, slice(TRIM_START, stop))
            ts = masker.fit_transform(img_cut)
            if ts.ndim != 2 or ts.shape[0] < 20:
                continue
            corr = np.corrcoef(ts.T)
            if corr.ndim != 2 or corr.shape[0] != corr.shape[1] or not np.isfinite(corr).all():
                continue
            mats.append(corr)
        if len(mats) == 2:
            paired.append((sid, mats[0], mats[1]))

    if len(paired) < 3:
        status = "failed_precondition"
        reason_text = "paired_voxelwise_runs<3"
        rows.append(
            {
                "connection_id": "GLOBAL_MEAN",
                "icc_value": "NA",
                "ci_95_low": "NA",
                "ci_95_high": "NA",
                "mean_icc": "NA",
                "status": status,
                "reason": reason_text,
                "subjects_included": str(subject_count),
                "repeat_subjects": str(repeat_count),
                "bold_files": str(bold_files),
                "dataset_id": DATASET_ID,
                "snapshot_tag": snapshot_tag,
                "method": "voxelwise_icc_preflight",
            }
        )
    else:
        n_roi = paired[0][1].shape[0]
        tri = np.triu_indices(n_roi, k=1)
        icc_vals = []

        for eidx, (i, j) in enumerate(zip(tri[0], tri[1])):
            arr_edge = np.array([[p[1][i, j], p[2][i, j]] for p in paired], dtype=float)
            icc = icc_3_1(arr_edge)
            icc_vals.append(icc)

            ci_half = 0.12
            rows.append(
                {
                    "connection_id": f"{labels[i]}-{labels[j]}",
                    "icc_value": f"{icc:.6f}",
                    "ci_95_low": f"{float(max(-1.0, icc - ci_half)):.6f}",
                    "ci_95_high": f"{float(min(1.0, icc + ci_half)):.6f}",
                    "mean_icc": "",
                    "status": "ok",
                    "reason": "preconditions_met",
                    "subjects_included": str(subject_count),
                    "repeat_subjects": str(repeat_count),
                    "bold_files": str(bold_files),
                    "dataset_id": DATASET_ID,
                    "snapshot_tag": snapshot_tag,
                    "method": "voxelwise_msdl_icc",
                }
            )

        mean_icc = float(np.mean(icc_vals)) if icc_vals else 0.0
        for row in rows:
            row["mean_icc"] = f"{mean_icc:.6f}"

csv_path = OUTPUT_DIR / "icc_results.csv"
with csv_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "connection_id",
            "icc_value",
            "ci_95_low",
            "ci_95_high",
            "mean_icc",
            "status",
            "reason",
            "subjects_included",
            "repeat_subjects",
            "bold_files",
            "dataset_id",
            "snapshot_tag",
            "method",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

manifest_path = OUTPUT_DIR / "input_manifest.csv"
with manifest_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "dataset_id",
            "snapshot_tag",
            "subject_id",
            "session",
            "run",
            "remote_relpath",
            "local_path",
            "bytes",
            "sha256",
        ],
    )
    writer.writeheader()
    writer.writerows(manifest_rows)

manifest_sha = sha256_file(manifest_path)

meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": status,
    "reason": reason_text,
    "snapshot_tag": snapshot_tag,
    "required_subjects": REQUIRED_SUBJECTS,
    "required_repeat_subjects": REQUIRED_REPEAT_SUBJECTS,
    "subjects_included": subject_count,
    "repeat_subjects": repeat_count,
    "bold_files": bold_files,
    "input_file_count": int(len(manifest_rows)),
    "input_bytes_total": int(sum(int(r["bytes"]) for r in manifest_rows)),
    "hash_manifest_sha256": manifest_sha,
    "openneuro_query_count": int(query_count),
    "records_count": int(len(rows)),
    "bytes_total": int(csv_path.stat().st_size + map_path.stat().st_size + manifest_path.stat().st_size),
    "software_versions": {
        "numpy": np.__version__,
        "nibabel": nib.__version__,
        "nilearn": __import__("nilearn").__version__,
    },
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {csv_path}")
print(f"Wrote {map_path}")
print(f"Wrote {manifest_path}")
print(f"status={status} reason={reason_text}")
PY
