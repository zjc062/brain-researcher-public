#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_conn_006_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_conn_006_voxelwise"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR CACHE_DIR

python3 - <<'PY'
import csv
import hashlib
import io
import json
import math
import os
import time
import re
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn import datasets, image
from nilearn.maskers import NiftiMapsMasker
from sklearn.decomposition import FastICA

TASK_ID = "OPENNEURO-CONN-006"
DATASET_ID = "ds001168"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

BYTE_BUDGET = int(os.environ.get("CONN006_MAX_TOTAL_BYTES", str(1700 * 1024 * 1024)))
MAX_RUNS = int(os.environ.get("CONN006_MAX_RUNS", "30"))
MAX_TIMEPOINTS = int(os.environ.get("CONN006_MAX_TP", "180"))
TRIM_START = int(os.environ.get("CONN006_TRIM_START", "4"))
N_COMPONENTS = int(os.environ.get("CONN006_COMPONENTS", "20"))

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
        if r["subject_id"] in participant_ids:
            by_subject.setdefault(r["subject_id"], []).append(r)

    chosen = []
    total_bytes = 0

    for sid in sorted(by_subject.keys()):
        if len(chosen) >= MAX_RUNS:
            break
        run = by_subject[sid][0]
        sz = max(1, int(run["size"]))
        if total_bytes + sz > BYTE_BUDGET:
            continue
        chosen.append(run)
        total_bytes += sz

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


def one_sample_t(vals: np.ndarray) -> float:
    vals = np.asarray(vals, dtype=float)
    if vals.size < 2:
        return 0.0
    m = float(np.mean(vals))
    s = float(np.std(vals, ddof=1))
    if s <= 1e-12:
        return 0.0
    return m / (s / math.sqrt(vals.size))


snapshot_tag, candidates, query_count = discover_runs()
participants = fetch_participants(snapshot_tag)
selected = select_runs(candidates, set(participants.keys()))
if len(selected) < 6:
    raise RuntimeError(f"Insufficient selected runs for ICA: {len(selected)}")

atlas = datasets.fetch_atlas_msdl(data_dir=str(CACHE_DIR / "atlas"))
atlas_img = atlas["maps"]

masker = NiftiMapsMasker(
    maps_img=atlas_img,
    standardize="zscore_sample",
    detrend=True,
    memory=str(CACHE_DIR / "nilearn_cache"),
    memory_level=1,
    verbose=0,
)

atlas_maps = nib.load(atlas_img)
atlas_data = np.asarray(atlas_maps.get_fdata(), dtype=np.float32)
if atlas_data.ndim != 4:
    raise RuntimeError("MSDL atlas maps expected 4D")

manifest_rows = []
run_sources = []

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
    if ts.ndim != 2 or ts.shape[0] < 25 or ts.shape[1] < N_COMPONENTS:
        continue

    run_sources.append(
        {
            "subject_id": run["subject_id"],
            "session": run["session"],
            "run_id": run["run_id"],
            "n_timepoints": int(ts.shape[0]),
            "timeseries": ts.astype(np.float32),
        }
    )

if len(run_sources) < 4:
    raise RuntimeError(f"Too few valid timeseries runs for ICA: {len(run_sources)}")

X = np.concatenate([r["timeseries"] for r in run_sources], axis=0)
if X.shape[0] < (N_COMPONENTS * 8):
    raise RuntimeError(f"Insufficient concatenated samples for ICA: {X.shape}")

ica = FastICA(n_components=N_COMPONENTS, random_state=0, whiten="unit-variance", max_iter=1000, tol=1e-4)
S = ica.fit_transform(X)  # samples x components
W = np.asarray(ica.components_, dtype=np.float32)  # components x atlas_rois

if W.shape[0] != N_COMPONENTS or W.shape[1] != atlas_data.shape[3]:
    raise RuntimeError(f"Unexpected ICA component shape {W.shape} vs atlas maps {atlas_data.shape}")

components_4d = np.zeros((*atlas_data.shape[:3], N_COMPONENTS), dtype=np.float32)
for c in range(N_COMPONENTS):
    comp = np.tensordot(atlas_data, W[c], axes=([3], [0]))
    comp = comp.astype(np.float32)
    s = float(np.std(comp))
    if s > 1e-6:
        comp = (comp - float(np.mean(comp))) / s
    components_4d[..., c] = comp

ica_path = OUTPUT_DIR / "ica_components.nii.gz"
nib.save(nib.Nifti1Image(components_4d, atlas_maps.affine, atlas_maps.header), str(ica_path))

# Split back sources per run for per-subject/session summaries
cursor = 0
component_time_rows = []
subject_session_values: dict[str, dict[str, list[np.ndarray]]] = {}
subject_values: dict[str, list[np.ndarray]] = {}

for r in run_sources:
    n = r["n_timepoints"]
    run_S = S[cursor : cursor + n, :]
    cursor += n

    sid = r["subject_id"]
    ses = r["session"]
    subject_values.setdefault(sid, []).append(np.mean(np.abs(run_S), axis=0))
    subject_session_values.setdefault(sid, {}).setdefault(ses, []).append(np.mean(np.abs(run_S), axis=0))

    mean_abs = np.mean(np.abs(run_S), axis=0)
    std_src = np.std(run_S, axis=0)
    for c in range(N_COMPONENTS):
        component_time_rows.append(
            {
                "subject_id": sid,
                "session": ses,
                "run_id": r["run_id"],
                "component_id": str(c + 1),
                "mean_abs_source": f"{float(mean_abs[c]):.6f}",
                "std_source": f"{float(std_src[c]):.6f}",
                "n_timepoints": str(int(n)),
            }
        )

component_time_rows.sort(key=lambda x: (x["subject_id"], x["session"], x["run_id"], int(x["component_id"])))

comp_ts_path = OUTPUT_DIR / "component_timeseries.csv"
with comp_ts_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["subject_id", "session", "run_id", "component_id", "mean_abs_source", "std_source", "n_timepoints"],
    )
    writer.writeheader()
    writer.writerows(component_time_rows)

# Component stats: test-retest difference where possible
stats_rows = []
paired_subjects = 0
for c in range(N_COMPONENTS):
    subj_means = []
    diffs = []
    ses1_vals = []
    ses2_vals = []

    for sid in sorted(subject_values.keys()):
        smean = np.mean(subject_values[sid], axis=0)
        subj_means.append(float(smean[c]))

        ses_map = subject_session_values.get(sid, {})
        s1 = ses_map.get("ses-1")
        s2 = ses_map.get("ses-2")
        if s1 and s2:
            v1 = float(np.mean(np.asarray(s1), axis=0)[c])
            v2 = float(np.mean(np.asarray(s2), axis=0)[c])
            ses1_vals.append(v1)
            ses2_vals.append(v2)
            diffs.append(v2 - v1)

    if c == 0:
        paired_subjects = len(diffs)

    t_val = one_sample_t(np.asarray(diffs, dtype=float)) if diffs else 0.0
    if len(ses1_vals) >= 2 and len(ses2_vals) >= 2:
        corr = float(np.corrcoef(np.asarray(ses1_vals), np.asarray(ses2_vals))[0, 1])
        if not np.isfinite(corr):
            corr = 0.0
    else:
        corr = 0.0

    stats_rows.append(
        {
            "component_id": str(c + 1),
            "group_diff_t": f"{float(t_val):.6f}",
            "stability_corr": f"{float(corr):.6f}",
            "component_mean": f"{float(np.mean(subj_means)):.6f}",
            "component_std": f"{float(np.std(subj_means)):.6f}",
            "n_subjects": str(len(subject_values)),
            "n_paired_subjects": str(len(diffs)),
            "snapshot_tag": snapshot_tag,
            "method": "voxelwise_msdl_fastica",
        }
    )

stats_path = OUTPUT_DIR / "stats.csv"
with stats_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "component_id",
            "group_diff_t",
            "stability_corr",
            "component_mean",
            "component_std",
            "n_subjects",
            "n_paired_subjects",
            "snapshot_tag",
            "method",
        ],
    )
    writer.writeheader()
    writer.writerows(stats_rows)

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
    "method": "voxelwise_msdl_fastica",
    "atlas_name": "MSDL",
    "n_components": N_COMPONENTS,
    "map_shape": [int(v) for v in components_4d.shape],
    "processing_subject_count": int(len(subject_values)),
    "processing_run_count": int(len(run_sources)),
    "paired_subject_count": int(paired_subjects),
    "input_file_count": int(len(manifest_rows)),
    "input_bytes_total": int(sum(int(r["bytes"]) for r in manifest_rows)),
    "hash_manifest_sha256": manifest_sha,
    "openneuro_query_count": int(query_count),
    "records_count": 4,
    "bytes_total": int(ica_path.stat().st_size + stats_path.stat().st_size + comp_ts_path.stat().st_size + manifest_path.stat().st_size),
    "software_versions": {
        "numpy": np.__version__,
        "nibabel": nib.__version__,
        "nilearn": __import__("nilearn").__version__,
        "scikit_learn": __import__("sklearn").__version__,
    },
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {ica_path}")
print(f"Wrote {stats_path}")
print(f"Wrote {comp_ts_path}")
print(f"Wrote {manifest_path}")
print(f"Subjects={len(subject_values)} Runs={len(run_sources)}")
PY
