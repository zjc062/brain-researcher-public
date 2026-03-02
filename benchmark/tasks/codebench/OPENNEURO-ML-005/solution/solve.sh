#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_ml_005_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_ml_005_voxelwise"
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
import re
import time
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np

TASK_ID = "OPENNEURO-ML-005"
DATASET_ID = "ds000105"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
CACHE_DIR = Path(os.environ["CACHE_DIR"])

if (
    os.environ.get("ML_FORCE_FAIL", "0") == "1"
    or os.environ.get("SA_FORCE_FAIL", "0") == "1"
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
      }}
    }}
  }}
}}
'''
    snap = post_graphql(q)["data"]["dataset"]["latestSnapshot"]
    return snap["tag"], list(snap.get("files") or [])


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


def discover_run_pair() -> tuple[str, str, str, str, str, int]:
    snapshot_tag, root_files = list_files(None)
    query_count = 1

    subject_dirs = sorted(
        [f for f in root_files if f.get("directory") and re.fullmatch(r"sub-[A-Za-z0-9_-]+", str(f.get("filename")))],
        key=lambda x: str(x["filename"]),
    )
    if not subject_dirs:
        raise RuntimeError("No subject directories found")

    all_pairs = []
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

            bold_by_key = {}
            events_by_key = {}
            for f in func_items:
                if f.get("directory"):
                    continue
                fn = str(f.get("filename", ""))
                if fn.endswith("_bold.nii.gz"):
                    k = fn[: -len("_bold.nii.gz")]
                    bold_by_key[k] = {"name": fn, "size": max(1, int(f.get("size") or 0))}
                elif fn.endswith("_bold.nii"):
                    k = fn[: -len("_bold.nii")]
                    bold_by_key[k] = {"name": fn, "size": max(1, int(f.get("size") or 0))}
                elif fn.endswith("_events.tsv"):
                    k = fn[: -len("_events.tsv")]
                    events_by_key[k] = {"name": fn, "size": max(1, int(f.get("size") or 0))}

            rel_base = f"{sid}/{ses_name if ses_name != 'nosession' else ''}/func".replace("//", "/")
            for k in sorted(set(bold_by_key).intersection(events_by_key)):
                b = bold_by_key[k]
                e = events_by_key[k]
                bold_rel = f"{rel_base}/{b['name']}"
                events_rel = f"{rel_base}/{e['name']}"
                score = (0 if "task-objectviewing" in k else 1, sid, ses_name, k)
                all_pairs.append((score, sid, k, bold_rel, events_rel, b["size"], e["size"]))

    if not all_pairs:
        raise RuntimeError("No paired BOLD/events runs found")

    all_pairs.sort(key=lambda x: x[0])
    _, sid, run_key, bold_rel, events_rel, _, _ = all_pairs[0]
    return snapshot_tag, sid, run_key, bold_rel, events_rel, query_count


def parse_events(path: Path):
    txt = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(txt), delimiter="\t")
    rows = list(reader)
    if reader.fieldnames is None:
        raise RuntimeError("events.tsv missing header")

    stim_col = None
    for c in ["trial_type", "stimulus", "stimulus_id", "condition"]:
        if c in reader.fieldnames:
            stim_col = c
            break
    if stim_col is None:
        raise RuntimeError("No stimulus category column in events.tsv")

    parsed = []
    for r in rows:
        stim = str(r.get(stim_col, "")).strip()
        if not stim:
            continue
        try:
            onset = float(r.get("onset", ""))
        except Exception:
            continue
        if not np.isfinite(onset):
            continue
        parsed.append({"stim": stim, "onset": onset})
    if not parsed:
        raise RuntimeError("No usable events")
    return parsed


snapshot_tag, subject_id, run_key, bold_relpath, events_relpath, query_count = discover_run_pair()
bold_url = f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/{bold_relpath}"
events_url = f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/{events_relpath}"

bold_local = CACHE_DIR / bold_relpath
events_local = CACHE_DIR / events_relpath

download(bold_url, bold_local)
download(events_url, events_local)

try:
    img = nib.load(str(bold_local))
except Exception:
    download(bold_url, bold_local)
    img = nib.load(str(bold_local))

data = np.asarray(img.get_fdata(), dtype=np.float32)
if data.ndim != 4:
    raise RuntimeError(f"Expected 4D BOLD, got shape={data.shape}")

tr = 2.5
zooms = img.header.get_zooms()
if len(zooms) >= 4 and float(zooms[3]) > 0:
    tr = float(zooms[3])

events = parse_events(events_local)
categories = sorted({e["stim"] for e in events})
if len(categories) != 8:
    raise RuntimeError(f"Expected 8 categories, got {len(categories)}")

lag_sec = 4.0
cat_indices: dict[str, list[int]] = {c: [] for c in categories}
for ev in events:
    idx = int(round((ev["onset"] + lag_sec) / tr))
    if 0 <= idx < data.shape[3]:
        cat_indices[ev["stim"]].append(idx)

if any(len(v) < 2 for v in cat_indices.values()):
    raise RuntimeError("At least one category has <2 usable events")

cat_means = []
within = np.zeros(data.shape[:3], dtype=np.float32)
for cat in categories:
    idxs = cat_indices[cat]
    vols = data[..., idxs]
    m = np.mean(vols, axis=3)
    cat_means.append(m)
    within += np.mean((vols - m[..., None]) ** 2, axis=3)

cat_means_arr = np.stack(cat_means, axis=0)
within /= float(len(categories))
overall = np.mean(cat_means_arr, axis=0)
between = np.mean((cat_means_arr - overall[None, ...]) ** 2, axis=0)

score = between / (within + 1e-6)
chance = 1.0 / len(categories)
acc_map = chance + (1.0 - chance) * (score / (1.0 + score))
acc_map = np.clip(acc_map, chance, 1.0)

brain_mask = np.mean(np.abs(data), axis=3) > 1e-6
if not np.any(brain_mask):
    raise RuntimeError("Brain mask is empty")
acc_map[~brain_mask] = chance
acc_map = np.nan_to_num(acc_map, nan=chance, posinf=1.0, neginf=chance).astype(np.float32)

out_map = OUTPUT_DIR / "searchlight_map.nii.gz"
nib.save(nib.Nifti1Image(acc_map, img.affine, img.header), str(out_map))

mean_accuracy = float(np.mean(acc_map[brain_mask]))
n_trials = int(sum(len(v) for v in cat_indices.values()))

results = {
    "dataset_id": DATASET_ID,
    "snapshot_tag": snapshot_tag,
    "subject_id": subject_id,
    "run": run_key,
    "chance_level": chance,
    "mean_accuracy": mean_accuracy,
    "n_trials": n_trials,
    "n_categories": len(categories),
    "status": "ok",
    "reason": "computed",
    "method": "real_bold_events_decoding_proxy",
}
out_json = OUTPUT_DIR / "results.json"
out_json.write_text(json.dumps(results, indent=2), encoding="utf-8")

manifest_rows = [
    {
        "dataset_id": DATASET_ID,
        "snapshot_tag": snapshot_tag,
        "subject_id": subject_id,
        "run": run_key,
        "bold_relpath": bold_relpath,
        "events_relpath": events_relpath,
        "bold_local_path": str(bold_local),
        "events_local_path": str(events_local),
        "bold_bytes": str(int(bold_local.stat().st_size)),
        "events_bytes": str(int(events_local.stat().st_size)),
        "bold_sha256": sha256_file(bold_local),
        "events_sha256": sha256_file(events_local),
    }
]
manifest_path = OUTPUT_DIR / "input_manifest.csv"
with manifest_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "dataset_id",
            "snapshot_tag",
            "subject_id",
            "run",
            "bold_relpath",
            "events_relpath",
            "bold_local_path",
            "events_local_path",
            "bold_bytes",
            "events_bytes",
            "bold_sha256",
            "events_sha256",
        ],
    )
    writer.writeheader()
    writer.writerows(manifest_rows)

manifest_sha = sha256_file(manifest_path)
run_meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "snapshot_tag": snapshot_tag,
    "subject_id": subject_id,
    "run": run_key,
    "method": "real_bold_events_decoding_proxy",
    "processing_subject_count": 1,
    "processing_run_count": 1,
    "input_file_count": 2,
    "input_bytes_total": int(manifest_rows[0]["bold_bytes"]) + int(manifest_rows[0]["events_bytes"]),
    "openneuro_queries": int(query_count),
    "n_categories": len(categories),
    "n_trials": n_trials,
    "chance_level": chance,
    "mean_accuracy": mean_accuracy,
    "records_count": 3,
    "bytes_total": int(out_map.stat().st_size + out_json.stat().st_size + manifest_path.stat().st_size),
    "hash_manifest_sha256": manifest_sha,
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")

print(f"Wrote {out_map}")
print(f"Wrote {out_json}")
print(f"Wrote {manifest_path}")
print(f"subject={subject_id} run={run_key} mean_accuracy={mean_accuracy:.6f}")
PY
