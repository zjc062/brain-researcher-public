#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_ml_012_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_ml_012_voxelwise"
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
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel

TASK_ID = "OPENNEURO-ML-012"
DATASET_ID = "ds000030"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

BYTE_BUDGET = int(os.environ.get("ML012_MAX_TOTAL_BYTES", str(1600 * 1024 * 1024)))
MAX_SUBJECTS = int(os.environ.get("ML012_MAX_SUBJECTS", "12"))
MAX_TIMEPOINTS = int(os.environ.get("ML012_MAX_TP", "180"))
TRIM_START = int(os.environ.get("ML012_TRIM_START", "4"))

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
        urls
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


def normalize_pid(pid: str) -> str:
    p = pid.strip()
    if p.startswith("sub-"):
        return p
    return f"sub-{p}"


def parse_float(value: str | None):
    if value is None:
        return None
    s = value.strip().lower()
    if s in {"", "n/a", "na", "nan", "none", "null"}:
        return None
    try:
        out = float(value)
    except ValueError:
        return None
    if not np.isfinite(out):
        return None
    return out


def fetch_participants(snapshot_tag: str, root_files: list[dict]) -> dict[str, float]:
    url = f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/participants.tsv"
    local = CACHE_DIR / "participants.tsv"
    downloaded = False
    try:
        download(url, local)
        downloaded = True
    except Exception:
        node = next((f for f in root_files if f.get("filename") == "participants.tsv" and (f.get("urls") or [])), None)
        if node is not None:
            download(node["urls"][0], local)
            downloaded = True

    if not downloaded or not local.exists() or local.stat().st_size == 0:
        return {}

    txt = local.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(txt), delimiter="\t")
    rows = list(reader)
    out = {}
    for r in rows:
        pid = r.get("participant_id")
        if not pid:
            continue
        age = parse_float(r.get("age"))
        if age is None:
            continue
        out[normalize_pid(pid)] = float(age)
    return out


def discover_runs() -> tuple[str, list[dict], int, list[dict]]:
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
                fn = str(f.get("filename", ""))
                if not re.search(r"_bold\.nii(\.gz)?$", fn):
                    continue
                rel_base = f"{sid}/{ses_name if ses_name != 'nosession' else ''}/func".replace("//", "/")
                relpath = f"{rel_base}/{fn}"
                run = fn.replace("_bold.nii.gz", "").replace("_bold.nii", "")
                runs.append(
                    {
                        "subject_id": sid,
                        "session": ses_name,
                        "run": run,
                        "remote_relpath": relpath,
                        "size": max(1, int(f.get("size") or 0)),
                        "url": f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/{relpath}",
                    }
                )

    runs.sort(key=lambda r: (r["subject_id"], r["session"], r["run"]))
    return snapshot_tag, runs, query_count, root_files


def select_one_run_per_subject(candidates: list[dict], age_map: dict[str, float]) -> list[dict]:
    by_subject = {}
    for r in candidates:
        sid = r["subject_id"]
        if sid not in age_map:
            continue
        by_subject.setdefault(sid, []).append(r)

    chosen = []
    total_bytes = 0
    for sid in sorted(by_subject.keys()):
        if len(chosen) >= MAX_SUBJECTS:
            break
        run = by_subject[sid][0]
        if total_bytes + run["size"] > BYTE_BUDGET:
            continue
        chosen.append(run)
        total_bytes += run["size"]
    chosen.sort(key=lambda r: (r["subject_id"], r["session"], r["run"]))
    return chosen


def extract_features_and_uncertainty(img: nib.Nifti1Image):
    arr = np.asarray(img.get_fdata(), dtype=np.float32)
    if arr.ndim != 4:
        raise RuntimeError("BOLD is not 4D")
    n_tp = int(arr.shape[3])
    if n_tp < TRIM_START + 20:
        raise RuntimeError("Insufficient timepoints")
    stop = min(n_tp, TRIM_START + MAX_TIMEPOINTS)
    arr = arr[..., TRIM_START:stop]

    mean_vol = np.mean(np.abs(arr), axis=3)
    mask = mean_vol > 1e-6
    if not np.any(mask):
        raise RuntimeError("Empty brain mask")

    ts = np.array([np.mean(arr[..., t][mask]) for t in range(arr.shape[3])], dtype=np.float64)
    temporal_std = np.std(arr, axis=3).astype(np.float32)
    tstd_mean = float(np.mean(temporal_std[mask]))

    feat = np.array([
        float(np.mean(ts)),
        float(np.std(ts)),
        tstd_mean,
    ], dtype=np.float64)

    denom = float(np.max(temporal_std)) + 1e-8
    unc = temporal_std / denom
    if float(np.std(unc)) <= 1e-8:
        base = mean_vol.astype(np.float32)
        bden = float(np.max(base)) + 1e-8
        unc = base / bden
    unc = np.nan_to_num(unc, nan=0.0, posinf=1.0, neginf=0.0).astype(np.float32)
    return feat, unc


snapshot_tag, candidates, query_count, root_files = discover_runs()
age_map = fetch_participants(snapshot_tag, root_files)
selected = select_one_run_per_subject(candidates, age_map)
if not selected:
    raise RuntimeError("No valid subject runs with age labels")

manifest_rows = []
sample_rows = []
unc_img_data = None
unc_affine = None
unc_header = None

for run in selected:
    local = CACHE_DIR / run["remote_relpath"]
    if not local.exists() or local.stat().st_size == 0:
        download(run["url"], local)

    try:
        img = nib.load(str(local))
    except Exception:
        download(run["url"], local)
        img = nib.load(str(local))

    try:
        feat, unc = extract_features_and_uncertainty(img)
    except Exception:
        continue

    sid = run["subject_id"]
    age = age_map.get(sid)
    if age is None:
        continue

    if unc_img_data is None:
        unc_img_data = unc
        unc_affine = img.affine
        unc_header = img.header

    sample_rows.append(
        {
            "subject_id": sid,
            "run": run["run"],
            "actual_age": float(age),
            "features": feat,
        }
    )

    manifest_rows.append(
        {
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "subject_id": sid,
            "run": run["run"],
            "remote_relpath": run["remote_relpath"],
            "local_path": str(local),
            "bytes": str(int(local.stat().st_size)),
            "sha256": sha256_file(local),
        }
    )

if not sample_rows:
    raise RuntimeError("No usable BOLD+age samples after extraction")
if unc_img_data is None:
    raise RuntimeError("Uncertainty map could not be computed")

X = np.stack([r["features"] for r in sample_rows], axis=0)
y = np.array([r["actual_age"] for r in sample_rows], dtype=np.float64)

status = "ok" if len(sample_rows) >= 2 else "failed_precondition"
reason = "computed" if status == "ok" else "subjects<2"

pred = None
std = None
if status == "ok":
    kernel = ConstantKernel(1.0) * RBF(length_scale=1.0) + WhiteKernel(noise_level=0.1)
    gpr = GaussianProcessRegressor(kernel=kernel, alpha=1e-6, normalize_y=True, optimizer=None)
    gpr.fit(X, y)
    pred, std = gpr.predict(X, return_std=True)

pred_rows = []
for i, r in enumerate(sample_rows):
    if status == "ok":
        p = float(pred[i])
        s = float(std[i])
        p_txt = f"{p:.8f}"
        s_txt = f"{max(0.0, s):.8f}"
    else:
        p_txt = "NA"
        s_txt = "NA"

    pred_rows.append(
        {
            "subject_id": r["subject_id"],
            "actual_age": f"{float(r['actual_age']):.8f}",
            "predicted_age": p_txt,
            "std_dev": s_txt,
            "status": status,
            "reason": reason,
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "method": "real_bold_gpr_age_prediction",
        }
    )

pred_path = OUTPUT_DIR / "age_preds.csv"
with pred_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "subject_id",
            "actual_age",
            "predicted_age",
            "std_dev",
            "status",
            "reason",
            "dataset_id",
            "snapshot_tag",
            "method",
        ],
    )
    writer.writeheader()
    writer.writerows(pred_rows)

unc_path = OUTPUT_DIR / "uncertainty.nii.gz"
nib.save(nib.Nifti1Image(unc_img_data.astype(np.float32), unc_affine, unc_header), str(unc_path))

manifest_path = OUTPUT_DIR / "input_manifest.csv"
with manifest_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "dataset_id",
            "snapshot_tag",
            "subject_id",
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
run_meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": status,
    "reason": reason,
    "snapshot_tag": snapshot_tag,
    "method": "real_bold_gpr_age_prediction",
    "processing_subject_count": int(len(sample_rows)),
    "processing_run_count": int(len(manifest_rows)),
    "input_file_count": int(len(manifest_rows)),
    "input_bytes_total": int(sum(int(r["bytes"]) for r in manifest_rows)),
    "openneuro_queries": int(query_count),
    "records_count": 3,
    "bytes_total": int(pred_path.stat().st_size + unc_path.stat().st_size + manifest_path.stat().st_size),
    "hash_manifest_sha256": manifest_sha,
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")

print(f"Wrote {pred_path}")
print(f"Wrote {unc_path}")
print(f"Wrote {manifest_path}")
print(f"status={status} reason={reason}")
print(f"subjects={len(sample_rows)} runs={len(manifest_rows)}")
PY
