#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_sa_010_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_sa_010_voxelwise"
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
from nilearn import datasets
from nilearn.maskers import NiftiMapsMasker
from scipy import stats

TASK_ID = "OPENNEURO-SA-010"
DATASET_ID = "ds000030"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

BYTE_BUDGET = int(os.environ.get("SA010_MAX_TOTAL_BYTES", str(1400 * 1024 * 1024)))
MAX_RUNS = int(os.environ.get("SA010_MAX_RUNS", "16"))
MAX_TIMEPOINTS = int(os.environ.get("SA010_MAX_TP", "160"))
TRIM_START = int(os.environ.get("SA010_TRIM_START", "4"))

MIN_SUBJECTS = int(os.environ.get("SA010_MIN_SUBJECTS", "8"))
MIN_SITES = int(os.environ.get("SA010_MIN_SITES", "2"))
MIN_AGE_SPAN = float(os.environ.get("SA010_MIN_AGE_SPAN", "5.0"))

OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
CACHE_DIR = Path(os.environ["CACHE_DIR"])

if (
    os.environ.get("ML_FORCE_FAIL", "0") == "1"
    or os.environ.get("SA_FORCE_FAIL", "0") == "1"
    or os.environ.get("STAT_FORCE_FAIL", "0") == "1"
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


def fetch_participants(snapshot_tag: str) -> tuple[dict[str, dict], int]:
    url = f"https://openneuro.org/crn/datasets/{DATASET_ID}/snapshots/{snapshot_tag}/files/participants.tsv"
    req = urllib.request.Request(url, headers={"User-Agent": "brain_researcher_benchmark"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            txt = resp.read().decode("utf-8")
    except Exception:
        return {}, 1

    reader = csv.DictReader(io.StringIO(txt), delimiter="\t")
    rows = list(reader)
    fieldnames = list(reader.fieldnames or [])

    site_col = None
    lower_lookup = {c.lower(): c for c in fieldnames}
    for c in [
        "site",
        "scanner_site",
        "acquisition_site",
        "scannerserialnumber",
        "scanner_serial_number",
        "scanner",
    ]:
        if c in lower_lookup:
            site_col = lower_lookup[c]
            break

    out = {}
    sites = set()
    for r in rows:
        pid = r.get("participant_id")
        if not pid:
            continue
        sid = normalize_pid(pid)
        age = parse_float(r.get("age"))
        site = str(r.get(site_col, "")).strip() if site_col else "single_site"
        if site:
            sites.add(site)
        out[sid] = {
            "age": age,
            "site": site if site else "single_site",
        }
    return out, max(1, len(sites))


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

                rel_base = f"{sid}/{ses_name if ses_name != 'nosession' else ''}/func".replace("//", "/")
                relpath = f"{rel_base}/{name}"
                run_id = name.replace("_bold.nii.gz", "").replace("_bold.nii", "")
                runs.append(
                    {
                        "subject_id": sid,
                        "session": ses_name,
                        "run": run_id,
                        "remote_relpath": relpath,
                        "size": max(1, int(f.get("size") or 0)),
                        "url": f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/{relpath}",
                    }
                )

    runs.sort(key=lambda r: (r["subject_id"], r["session"], r["run"]))
    return snapshot_tag, runs, query_count


def select_runs(candidates: list[dict], participant_map: dict[str, dict]) -> list[dict]:
    by_subject: dict[str, list[dict]] = {}
    for r in candidates:
        sid = r["subject_id"]
        if sid not in participant_map:
            continue
        by_subject.setdefault(sid, []).append(r)

    chosen = []
    total_bytes = 0

    for sid in sorted(by_subject.keys()):
        if len(chosen) >= MAX_RUNS:
            break
        run = by_subject[sid][0]
        if total_bytes + run["size"] > BYTE_BUDGET:
            continue
        chosen.append(run)
        total_bytes += run["size"]

    extras = []
    for sid in sorted(by_subject.keys()):
        extras.extend(by_subject[sid][1:])
    for run in extras:
        if len(chosen) >= MAX_RUNS:
            break
        if total_bytes + run["size"] > BYTE_BUDGET:
            continue
        chosen.append(run)
        total_bytes += run["size"]

    chosen.sort(key=lambda r: (r["subject_id"], r["session"], r["run"]))
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


def extract_metric(masker: NiftiMapsMasker, img: nib.Nifti1Image) -> tuple[float, int]:
    if len(img.shape) != 4:
        raise RuntimeError("BOLD image is not 4D")
    n_tp = int(img.shape[3])
    if n_tp < TRIM_START + 20:
        raise RuntimeError("Insufficient timepoints")
    stop = min(n_tp, TRIM_START + MAX_TIMEPOINTS)
    trimmed = img.slicer[..., TRIM_START:stop]
    ts = np.asarray(masker.fit_transform(trimmed), dtype=np.float64)
    if ts.ndim != 2 or ts.shape[0] < 20 or ts.shape[1] < 2:
        raise RuntimeError("Invalid atlas timeseries")
    corr = np.corrcoef(ts.T)
    iu = np.triu_indices(corr.shape[0], k=1)
    metric = float(np.nanmean(np.abs(corr[iu])))
    if not np.isfinite(metric):
        raise RuntimeError("Connectivity metric non-finite")
    return metric, int(ts.shape[0])


snapshot_tag, candidates, query_count = discover_runs()
participants, sites_included = fetch_participants(snapshot_tag)
selected = select_runs(candidates, participants)

atlas = datasets.fetch_atlas_msdl(data_dir=str(CACHE_DIR / "atlas"))
masker = NiftiMapsMasker(
    maps_img=atlas["maps"],
    standardize="zscore_sample",
    detrend=True,
    memory=str(CACHE_DIR / "nilearn_cache"),
    memory_level=1,
    verbose=0,
)

manifest_rows = []
subject_metrics: dict[str, list[float]] = {}
subject_timepoints: dict[str, list[int]] = {}

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
        metric, n_tp = extract_metric(masker, img)
    except Exception:
        continue

    sid = run["subject_id"]
    subject_metrics.setdefault(sid, []).append(metric)
    subject_timepoints.setdefault(sid, []).append(n_tp)

    manifest_rows.append(
        {
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "subject_id": sid,
            "session": run["session"],
            "run": run["run"],
            "remote_relpath": run["remote_relpath"],
            "local_path": str(local),
            "bytes": str(int(local.stat().st_size)),
            "sha256": sha256_file(local),
        }
    )

usable_subjects = []
for sid, vals in sorted(subject_metrics.items()):
    age = participants.get(sid, {}).get("age")
    if age is None:
        continue
    usable_subjects.append(
        {
            "subject_id": sid,
            "age": float(age),
            "metric": float(np.mean(vals)),
            "n_runs": int(len(vals)),
            "n_timepoints": int(sum(subject_timepoints.get(sid, []))),
        }
    )

ages = np.asarray([r["age"] for r in usable_subjects], dtype=np.float64)
metrics = np.asarray([r["metric"] for r in usable_subjects], dtype=np.float64)
age_span = float(np.max(ages) - np.min(ages)) if ages.size else 0.0

reasons = []
if len(usable_subjects) < MIN_SUBJECTS:
    reasons.append(f"subjects<{MIN_SUBJECTS}")
if sites_included < MIN_SITES:
    reasons.append(f"sites<{MIN_SITES}")
if age_span < MIN_AGE_SPAN:
    reasons.append(f"age_span<{MIN_AGE_SPAN}")

status = "failed_precondition" if reasons else "ok"
reason = ";".join(reasons) if reasons else "computed"

age_squared_p = "NA"
beta_age = "NA"
beta_age2 = "NA"
if status == "ok":
    X = np.column_stack([np.ones_like(ages), ages, ages * ages])
    y = metrics
    n = int(X.shape[0])
    p = int(X.shape[1])
    xtx = X.T @ X
    xtx_inv = np.linalg.pinv(xtx)
    beta = xtx_inv @ X.T @ y
    resid = y - (X @ beta)
    df = max(1, n - p)
    sigma2 = float((resid @ resid) / df)
    se_beta2 = float(np.sqrt(max(1e-18, sigma2 * xtx_inv[2, 2])))
    t_stat = float(beta[2] / se_beta2) if se_beta2 > 0 else 0.0
    p_val = float(2.0 * (1.0 - stats.t.cdf(abs(t_stat), df=df)))
    age_squared_p = f"{p_val:.8f}"
    beta_age = f"{float(beta[1]):.8f}"
    beta_age2 = f"{float(beta[2]):.8f}"

rows = [
    {
        "connection": "GLOBAL_DMN_MEAN_ABS_FC",
        "age_squared_p": age_squared_p,
        "beta_age": beta_age,
        "beta_age2": beta_age2,
        "status": status,
        "reason": reason,
        "subjects_included": str(int(len(usable_subjects))),
        "sites_included": str(int(sites_included)),
        "age_min": "" if not usable_subjects else f"{float(np.min(ages)):.4f}",
        "age_max": "" if not usable_subjects else f"{float(np.max(ages)):.4f}",
        "age_span": f"{float(age_span):.4f}",
        "runs_used": str(int(sum(r["n_runs"] for r in usable_subjects))),
        "dataset_id": DATASET_ID,
        "snapshot_tag": snapshot_tag,
        "method": "real_bold_quadratic_age_model",
    }
]

out_csv = OUTPUT_DIR / "age_model_results.csv"
with out_csv.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "connection",
            "age_squared_p",
            "beta_age",
            "beta_age2",
            "status",
            "reason",
            "subjects_included",
            "sites_included",
            "age_min",
            "age_max",
            "age_span",
            "runs_used",
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
bytes_total = int(out_csv.stat().st_size + manifest_path.stat().st_size)
meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": status,
    "reason": reason,
    "snapshot_tag": snapshot_tag,
    "method": "real_bold_quadratic_age_model",
    "subjects_included": int(len(usable_subjects)),
    "sites_included": int(sites_included),
    "age_span": float(age_span),
    "processing_run_count": int(len(manifest_rows)),
    "input_file_count": int(len(manifest_rows)),
    "input_bytes_total": int(sum(int(r["bytes"]) for r in manifest_rows)),
    "openneuro_queries": int(query_count),
    "records_count": 2,
    "bytes_total": int(bytes_total),
    "hash_manifest_sha256": manifest_sha,
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {out_csv}")
print(f"Wrote {manifest_path}")
print(f"status={status} reason={reason}")
print(f"Subjects={len(usable_subjects)} Runs={len(manifest_rows)} Sites={sites_included}")
PY
