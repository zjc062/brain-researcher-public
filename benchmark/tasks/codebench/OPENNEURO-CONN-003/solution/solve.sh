#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_conn_003_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_conn_003_voxelwise"
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
from scipy import stats

TASK_ID = "OPENNEURO-CONN-003"
DATASET_ID = "ds002424"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

BYTE_BUDGET = int(os.environ.get("CONN003_MAX_TOTAL_BYTES", str(2000 * 1024 * 1024)))
MAX_RUNS = int(os.environ.get("CONN003_MAX_RUNS", "48"))
MAX_TIMEPOINTS = int(os.environ.get("CONN003_MAX_TP", "180"))
TRIM_START = int(os.environ.get("CONN003_TRIM_START", "4"))
PERMUTATIONS = int(os.environ.get("CONN003_PERMUTATIONS", "0"))
CLUSTER_T = float(os.environ.get("CONN003_CLUSTER_T", "3.0"))

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


def parse_dx(value: str | None):
    if value is None:
        return None
    s = value.strip().lower()
    if s in {"", "n/a", "na", "nan", "none", "null"}:
        return None
    try:
        out = int(float(value))
    except ValueError:
        return None
    if out not in {0, 1}:
        return None
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


def select_runs(candidates: list[dict], labeled_subjects: set[str]) -> list[dict]:
    by_subject: dict[str, list[dict]] = {}
    for r in candidates:
        if r["subject_id"] in labeled_subjects:
            by_subject.setdefault(r["subject_id"], []).append(r)

    chosen = []
    total_bytes = 0

    # First pass: one run per subject for broad group coverage.
    for sid in sorted(by_subject.keys()):
        if len(chosen) >= MAX_RUNS:
            break
        run = by_subject[sid][0]
        sz = max(1, int(run["size"]))
        if total_bytes + sz > BYTE_BUDGET:
            continue
        chosen.append(run)
        total_bytes += sz

    # Second pass: add additional runs while budget allows.
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


def welch_t_matrix(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    if x.shape[0] < 2 or y.shape[0] < 2:
        return np.zeros(x.shape[1], dtype=float)
    mx = np.mean(x, axis=0)
    my = np.mean(y, axis=0)
    vx = np.var(x, axis=0, ddof=1)
    vy = np.var(y, axis=0, ddof=1)
    denom = np.sqrt(vx / x.shape[0] + vy / y.shape[0])
    denom[denom <= 1e-12] = np.inf
    t = (mx - my) / denom
    t[~np.isfinite(t)] = 0.0
    return t


def welch_pvalues(x: np.ndarray, y: np.ndarray, t_vals: np.ndarray) -> np.ndarray:
    nx = x.shape[0]
    ny = y.shape[0]
    vx = np.var(x, axis=0, ddof=1)
    vy = np.var(y, axis=0, ddof=1)
    denom = vx / nx + vy / ny
    df_num = denom**2
    df_den = (vx**2) / (max(nx - 1, 1) * (nx**2)) + (vy**2) / (max(ny - 1, 1) * (ny**2)) + 1e-12
    df = np.maximum(df_num / df_den, 1.0)
    p = 2.0 * stats.t.sf(np.abs(t_vals), df=df)
    p = np.clip(p, 0.0, 1.0)
    p[~np.isfinite(p)] = 1.0
    return p


snapshot_tag, candidates, query_count = discover_runs()
participants = fetch_participants(snapshot_tag)

labels = {}
for sid, row in participants.items():
    dx = parse_dx(row.get("ADHD_diagnosis"))
    if dx is not None:
        labels[sid] = dx

selected = select_runs(candidates, set(labels.keys()))
if not selected:
    raise RuntimeError("No eligible runs selected for voxelwise NBS")

atlas = datasets.fetch_atlas_msdl(data_dir=str(CACHE_DIR / "atlas"))
atlas_img = atlas["maps"]
roi_labels = list(atlas["labels"])

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
    if ts.ndim != 2 or ts.shape[0] < 25 or ts.shape[1] < 5:
        continue

    corr = np.corrcoef(ts.T)
    if corr.ndim != 2 or corr.shape[0] != corr.shape[1]:
        continue
    if not np.isfinite(corr).all():
        continue

    sid = run["subject_id"]
    subject_mats.setdefault(sid, []).append(corr.astype(np.float32))

subjects = sorted([sid for sid in subject_mats.keys() if sid in labels])
if len(subjects) < 8:
    raise RuntimeError(f"Insufficient subjects with valid FC matrices: {len(subjects)}")

subject_mean_mats = np.stack([np.mean(subject_mats[sid], axis=0) for sid in subjects], axis=0).astype(np.float32)
y = np.asarray([labels[sid] for sid in subjects], dtype=int)

n_adhd = int(np.sum(y == 1))
n_control = int(np.sum(y == 0))
if n_adhd < 2 or n_control < 2:
    raise RuntimeError("Need >=2 subjects per group for edge-wise statistics")

n_roi = subject_mean_mats.shape[1]
tri = np.triu_indices(n_roi, k=1)
edge_values = subject_mean_mats[:, tri[0], tri[1]]

obs_t = welch_t_matrix(edge_values[y == 1], edge_values[y == 0])
adhd_mean = np.mean(edge_values[y == 1], axis=0)
control_mean = np.mean(edge_values[y == 0], axis=0)

abs_obs = np.abs(obs_t)
p_unc = welch_pvalues(edge_values[y == 1], edge_values[y == 0], obs_t)
p_corr = np.clip(p_unc * float(len(p_unc)), 0.0, 1.0)

sig_mask = (abs_obs >= CLUSTER_T) & (p_corr < 0.05)

all_rows = []
sig_rows = []
for eidx, (i, j) in enumerate(zip(tri[0], tri[1])):
    row = {
        "roi_1": roi_labels[i],
        "roi_2": roi_labels[j],
        "t_stat": f"{float(obs_t[eidx]):.6f}",
        "p_uncorrected": f"{float(p_unc[eidx]):.6e}",
        "p_corrected": f"{float(p_corr[eidx]):.6e}",
        "adhd_mean": f"{float(adhd_mean[eidx]):.6f}",
        "control_mean": f"{float(control_mean[eidx]):.6f}",
        "n_adhd": str(n_adhd),
        "n_control": str(n_control),
        "significant": "1" if sig_mask[eidx] else "0",
    }
    all_rows.append(row)
    if sig_mask[eidx]:
        sig_rows.append(
            {
                "roi_1": row["roi_1"],
                "roi_2": row["roi_2"],
                "t_stat": row["t_stat"],
                "p_val": row["p_corrected"],
                "adhd_mean": row["adhd_mean"],
                "control_mean": row["control_mean"],
                "n_adhd": row["n_adhd"],
                "n_control": row["n_control"],
            }
        )

all_rows.sort(key=lambda r: (float(r["p_corrected"]), -abs(float(r["t_stat"])), r["roi_1"], r["roi_2"]))
sig_rows.sort(key=lambda r: (float(r["p_val"]), -abs(float(r["t_stat"])), r["roi_1"], r["roi_2"]))

stats_path = OUTPUT_DIR / "group_connectivity_stats.csv"
with stats_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
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
        ],
    )
    writer.writeheader()
    writer.writerows(all_rows)

altered_path = OUTPUT_DIR / "altered_edges.csv"
with altered_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["roi_1", "roi_2", "t_stat", "p_val", "adhd_mean", "control_mean", "n_adhd", "n_control"],
    )
    writer.writeheader()
    writer.writerows(sig_rows)

summary_path = OUTPUT_DIR / "nbs_results.txt"
summary_lines = [
    f"dataset_id: {DATASET_ID}",
    f"snapshot_tag: {snapshot_tag}",
    "method: voxelwise_msdl_nbs_proxy",
    "status: ok",
    "reason: computed",
    f"subjects_used: {len(subjects)}",
    f"adhd_subjects: {n_adhd}",
    f"control_subjects: {n_control}",
    f"cluster_forming_t: {CLUSTER_T}",
    f"permutations: {PERMUTATIONS}",
    f"significant_edges: {len(sig_rows)}",
]
summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

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
    "method": "voxelwise_msdl_nbs_proxy",
    "atlas_name": "MSDL",
    "processing_subject_count": int(len(subjects)),
    "processing_run_count": int(sum(len(subject_mats[sid]) for sid in subjects)),
    "subjects_used": int(len(subjects)),
    "adhd_subjects": n_adhd,
    "control_subjects": n_control,
    "cluster_forming_t": float(CLUSTER_T),
    "permutations": int(PERMUTATIONS),
    "pvalue_method": "welch_t_two_sided",
    "multiple_comparison": "bonferroni",
    "significant_edges": int(len(sig_rows)),
    "input_file_count": int(len(manifest_rows)),
    "input_bytes_total": int(sum(int(r["bytes"]) for r in manifest_rows)),
    "hash_manifest_sha256": manifest_sha,
    "openneuro_query_count": int(query_count),
    "records_count": 4,
    "bytes_total": int(
        stats_path.stat().st_size + altered_path.stat().st_size + summary_path.stat().st_size + manifest_path.stat().st_size
    ),
    "software_versions": {
        "numpy": np.__version__,
        "nibabel": nib.__version__,
        "nilearn": __import__("nilearn").__version__,
    },
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {stats_path}")
print(f"Wrote {altered_path}")
print(f"Wrote {summary_path}")
print(f"Wrote {manifest_path}")
print(f"Subjects={len(subjects)} SignificantEdges={len(sig_rows)}")
PY
