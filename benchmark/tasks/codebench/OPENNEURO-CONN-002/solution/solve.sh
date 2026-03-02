#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_conn_002_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_conn_002_voxelwise"
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
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn import datasets, image
from nilearn.maskers import NiftiMapsMasker

TASK_ID = "OPENNEURO-CONN-002"
DATASET_ID = "ds001168"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

BYTE_BUDGET = int(os.environ.get("CONN002_MAX_TOTAL_BYTES", str(1600 * 1024 * 1024)))
MAX_RUNS = int(os.environ.get("CONN002_MAX_RUNS", "32"))
MAX_TIMEPOINTS = int(os.environ.get("CONN002_MAX_TP", "180"))
TRIM_START = int(os.environ.get("CONN002_TRIM_START", "4"))

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


def fetch_participants(snapshot_tag: str) -> dict[str, dict[str, str]]:
    url = f"https://openneuro.org/crn/datasets/{DATASET_ID}/snapshots/{snapshot_tag}/files/participants.tsv"
    req = urllib.request.Request(url, headers={"User-Agent": "brain_researcher_benchmark"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        txt = resp.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(txt), delimiter="\t")
    rows = list(reader)
    if reader.fieldnames is None or "participant_id" not in reader.fieldnames:
        raise RuntimeError("participants.tsv missing participant_id")
    return {r["participant_id"].strip(): r for r in rows if r.get("participant_id")}


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
    by_subject: dict[str, list[dict]] = {}
    for r in candidates:
        if r["subject_id"] not in participant_ids:
            continue
        by_subject.setdefault(r["subject_id"], []).append(r)

    chosen = []
    total_bytes = 0

    # First pass: maximize subject coverage (one run per subject)
    for sid in sorted(by_subject.keys()):
        if len(chosen) >= MAX_RUNS:
            break
        run = by_subject[sid][0]
        sz = max(1, int(run["size"]))
        if total_bytes + sz > BYTE_BUDGET:
            continue
        chosen.append(run)
        total_bytes += sz

    # Second pass: add extra runs while budget allows
    extras = []
    for sid in sorted(by_subject.keys()):
        extras.extend(by_subject[sid][1:])
    for run in extras:
        if len(chosen) >= MAX_RUNS:
            break
        sz = max(1, int(run["size"]))
        if total_bytes + sz > BYTE_BUDGET:
            continue
        chosen.append(run)
        total_bytes += sz

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


def safe_tr(img: nib.Nifti1Image) -> float:
    zooms = img.header.get_zooms()
    if len(zooms) >= 4 and float(zooms[3]) > 0:
        return float(zooms[3])
    return 2.0


snapshot_tag, candidates, query_count = discover_runs()
participants = fetch_participants(snapshot_tag)
selected = select_runs(candidates, set(participants.keys()))
if not selected:
    raise RuntimeError("No eligible BOLD runs selected for voxelwise connectivity")

atlas = datasets.fetch_atlas_msdl(data_dir=str(CACHE_DIR / "atlas"))
atlas_img = atlas["maps"]
atlas_labels = list(atlas["labels"])
atlas_networks = [str(x) for x in atlas.get("networks", [])]

if atlas_networks and len(atlas_networks) == len(atlas_labels):
    dmn_idx = [i for i, net in enumerate(atlas_networks) if "DMN" in net.upper()]
else:
    dmn_idx = [i for i, label in enumerate(atlas_labels) if "DMN" in label.upper()]
if len(dmn_idx) < 2:
    dmn_idx = list(range(min(8, len(atlas_labels))))

masker = NiftiMapsMasker(
    maps_img=atlas_img,
    standardize="zscore_sample",
    detrend=True,
    memory=str(CACHE_DIR / "nilearn_cache"),
    memory_level=1,
    verbose=0,
)

manifest_rows = []
subject_mats: dict[str, list[np.ndarray]] = {}
subject_tp: dict[str, list[int]] = {}

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

    img = nib.load(str(local_path))
    n_tp = int(img.shape[3]) if len(img.shape) == 4 else 0
    if n_tp < (TRIM_START + 30):
        continue

    stop = min(n_tp, TRIM_START + MAX_TIMEPOINTS)
    img_cut = image.index_img(img, slice(TRIM_START, stop))
    ts = masker.fit_transform(img_cut)
    if ts.ndim != 2 or ts.shape[0] < 25 or ts.shape[1] < len(dmn_idx):
        continue

    dmn_ts = ts[:, dmn_idx]
    corr = np.corrcoef(dmn_ts.T)
    if corr.ndim != 2 or corr.shape[0] != corr.shape[1]:
        continue
    if not np.isfinite(corr).all():
        continue

    sid = run["subject_id"]
    subject_mats.setdefault(sid, []).append(corr.astype(np.float32))
    subject_tp.setdefault(sid, []).append(int(ts.shape[0]))

if not subject_mats:
    raise RuntimeError("No valid subject-level DMN matrices could be computed")

subjects = sorted(subject_mats.keys())
mat_stack = np.stack([np.mean(subject_mats[sid], axis=0) for sid in subjects], axis=0).astype(np.float32)

summary_rows = []
for idx, sid in enumerate(subjects):
    mat = mat_stack[idx]
    triu = mat[np.triu_indices(mat.shape[0], k=1)]
    summary_rows.append(
        {
            "subject_id": sid,
            "n_runs": str(len(subject_mats[sid])),
            "n_timepoints": str(int(np.sum(subject_tp[sid]))),
            "mean_dmn_conn": f"{float(np.mean(triu)):.6f}",
            "std_dmn_conn": f"{float(np.std(triu)):.6f}",
            "n_edges": str(int(triu.size)),
        }
    )

summary_rows.sort(key=lambda r: r["subject_id"])

npz_path = OUTPUT_DIR / "subject_connectivity_matrices.npz"
np.savez_compressed(
    npz_path,
    subject_ids=np.asarray(subjects, dtype="U64"),
    dmn_labels=np.asarray([atlas_labels[i] for i in dmn_idx], dtype="U128"),
    matrices=mat_stack,
)

summary_path = OUTPUT_DIR / "dmn_summary.csv"
with summary_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["subject_id", "n_runs", "n_timepoints", "mean_dmn_conn", "std_dmn_conn", "n_edges"],
    )
    writer.writeheader()
    writer.writerows(summary_rows)

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
    "status": "ok",
    "reason": "computed",
    "snapshot_tag": snapshot_tag,
    "atlas_name": "MSDL",
    "dmn_roi_count": int(len(dmn_idx)),
    "processing_subject_count": int(len(subjects)),
    "processing_run_count": int(sum(len(v) for v in subject_mats.values())),
    "input_file_count": int(len(manifest_rows)),
    "input_bytes_total": int(sum(int(r["bytes"]) for r in manifest_rows)),
    "hash_manifest_sha256": manifest_sha,
    "openneuro_query_count": int(query_count),
    "records_count": 3,
    "bytes_total": int(npz_path.stat().st_size + summary_path.stat().st_size + manifest_path.stat().st_size),
    "software_versions": {
        "numpy": np.__version__,
        "nibabel": nib.__version__,
        "nilearn": __import__("nilearn").__version__,
    },
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {npz_path}")
print(f"Wrote {summary_path}")
print(f"Wrote {manifest_path}")
print(f"Subjects={len(subjects)} Runs={sum(len(v) for v in subject_mats.values())}")
PY
