#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_qc_003_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_qc_003_voxelwise"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR CACHE_DIR

python3 - <<'PY'
import csv
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np

TASK_ID = "OPENNEURO-QC-003"
DATASET_ID = "ds002424"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

BYTE_BUDGET = int(os.environ.get("QC003_MAX_TOTAL_BYTES", str(1400 * 1024 * 1024)))
MAX_SUBJECTS = int(os.environ.get("QC003_MAX_SUBJECTS", "18"))

OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
CACHE_DIR = Path(os.environ["CACHE_DIR"])
errors: list[str] = []

if (
    os.environ.get("QC_FORCE_FAIL", "0") == "1"
    or os.environ.get("ML_FORCE_FAIL", "0") == "1"
):
    raise RuntimeError("forced_failure")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def post_graphql(query: str) -> dict:
    last_err = None
    for attempt in range(1, 7):
        try:
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
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, RuntimeError, OSError) as exc:
            last_err = exc
            if attempt < 6:
                time.sleep(min(12, 2**attempt))
    raise RuntimeError(f"OpenNeuro GraphQL unavailable after retries: {last_err}")


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


def discover_anatomical_candidates() -> tuple[str, list[dict], int]:
    snapshot_tag, root_files = list_files(None)
    query_count = 1

    subject_dirs = sorted(
        [f for f in root_files if f.get("directory") and re.fullmatch(r"sub-[A-Za-z0-9_-]+", str(f.get("filename")))],
        key=lambda x: str(x["filename"]),
    )

    candidates = []
    for sub in subject_dirs:
        sid = str(sub["filename"])
        try:
            _, sub_items = list_files(sub["key"])
            query_count += 1
        except Exception as exc:
            errors.append(f"list_subject:{sid}:{type(exc).__name__}")
            continue

        ses_dirs = [x for x in sub_items if x.get("directory") and str(x.get("filename", "")).startswith("ses-")]
        if not ses_dirs:
            ses_dirs = [{"filename": "nosession", "key": sub["key"], "directory": True}]

        for ses in sorted(ses_dirs, key=lambda x: str(x["filename"])):
            if ses["key"] != sub["key"]:
                try:
                    _, ses_items = list_files(ses["key"])
                    query_count += 1
                except Exception as exc:
                    errors.append(f"list_session:{sid}:{ses.get('filename')}:{type(exc).__name__}")
                    continue
                ses_name = str(ses["filename"])
            else:
                ses_items = sub_items
                ses_name = "nosession"

            anat_dir = next((x for x in ses_items if x.get("directory") and x.get("filename") == "anat"), None)
            if anat_dir is None:
                continue

            try:
                _, anat_items = list_files(anat_dir["key"])
                query_count += 1
            except Exception as exc:
                errors.append(f"list_anat:{sid}:{ses_name}:{type(exc).__name__}")
                continue
            for node in sorted(anat_items, key=lambda x: str(x.get("filename", ""))):
                if node.get("directory"):
                    continue
                fn = str(node.get("filename", ""))
                if not re.search(r"_T1w\.nii(\.gz)?$", fn):
                    continue
                rel_base = f"{sid}/{ses_name if ses_name != 'nosession' else ''}/anat".replace("//", "/")
                relpath = f"{rel_base}/{fn}"
                candidates.append(
                    {
                        "subject_id": sid,
                        "session": ses_name,
                        "anat_relpath": relpath,
                        "size": max(1, int(node.get("size") or 0)),
                        "url": f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/{relpath}",
                    }
                )

    candidates.sort(key=lambda r: (r["subject_id"], r["session"], r["anat_relpath"]))
    return snapshot_tag, candidates, query_count


def select_one_anat_per_subject(candidates: list[dict]) -> list[dict]:
    by_subject: dict[str, list[dict]] = {}
    for c in candidates:
        by_subject.setdefault(c["subject_id"], []).append(c)

    selected = []
    total_bytes = 0
    for sid in sorted(by_subject.keys()):
        if len(selected) >= MAX_SUBJECTS:
            break
        run = sorted(by_subject[sid], key=lambda x: (x["size"], x["session"], x["anat_relpath"]))[0]
        if total_bytes + run["size"] > BYTE_BUDGET:
            continue
        selected.append(run)
        total_bytes += run["size"]

    return selected


def compute_qc_metrics(img: nib.Nifti1Image) -> tuple[float, float, float]:
    arr = np.asarray(img.get_fdata(), dtype=np.float32)
    if arr.ndim == 4:
        arr = np.mean(arr, axis=3)
    if arr.ndim != 3:
        raise RuntimeError("Anatomical image is not 3D/4D")

    finite = np.isfinite(arr)
    if int(np.sum(finite)) < 2000:
        raise RuntimeError("Too few finite voxels")

    vals = arr[finite]
    p20, p80 = np.percentile(vals, [20.0, 80.0])
    bg_mask = finite & (arr <= p20)
    brain_mask = finite & (arr >= p80)

    if int(np.sum(bg_mask)) < 500 or int(np.sum(brain_mask)) < 500:
        p30, p70 = np.percentile(vals, [30.0, 70.0])
        bg_mask = finite & (arr <= p30)
        brain_mask = finite & (arr >= p70)

    if int(np.sum(bg_mask)) < 500 or int(np.sum(brain_mask)) < 500:
        raise RuntimeError("Could not derive stable foreground/background masks")

    bg = arr[bg_mask].astype(np.float64)
    brain = arr[brain_mask].astype(np.float64)

    mean_bg = float(np.mean(bg))
    std_bg = float(np.std(bg))
    mean_brain = float(np.mean(brain))
    std_brain = float(np.std(brain))

    snr = mean_brain / (std_bg + 1e-6)
    cnr = (mean_brain - mean_bg) / float(np.sqrt(std_brain**2 + std_bg**2 + 1e-6))

    z_bg = np.abs((bg - mean_bg) / (std_bg + 1e-6))
    qi1 = float(np.mean(z_bg > 3.0))
    qi1 = float(np.clip(qi1, 0.0, 1.0))

    return float(snr), float(cnr), qi1


def rating_from_metrics(snr: float, cnr: float, qi1: float) -> str:
    if snr < 5.0 or cnr < 0.2 or qi1 > 0.25:
        return "fail"
    if snr < 10.0 or cnr < 0.5 or qi1 > 0.15:
        return "warn"
    return "pass"


snapshot_tag, candidates, query_count = discover_anatomical_candidates()
selected = select_one_anat_per_subject(candidates)

manifest_rows = []
qc_rows = []
processed_subjects = set()

for run in selected:
    local = CACHE_DIR / run["anat_relpath"]
    if not local.exists() or local.stat().st_size == 0:
        try:
            download(run["url"], local)
        except Exception as exc:
            errors.append(f"download:{run['subject_id']}:{exc}")
            continue

    try:
        img = nib.load(str(local))
    except Exception:
        try:
            download(run["url"], local)
            img = nib.load(str(local))
        except Exception as exc:
            errors.append(f"load:{run['subject_id']}:{exc}")
            continue

    try:
        snr, cnr, qi1 = compute_qc_metrics(img)
    except Exception as exc:
        errors.append(f"metrics:{run['subject_id']}:{exc}")
        continue

    processed_subjects.add(run["subject_id"])
    rating = rating_from_metrics(snr, cnr, qi1)
    qc_rows.append(
        {
            "subject_id": run["subject_id"],
            "snr": f"{snr:.8f}",
            "cnr": f"{cnr:.8f}",
            "qi1": f"{qi1:.8f}",
            "overall_rating": rating,
            "status": "ok",
            "reason": "computed",
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "method": "real_t1w_intensity_qc",
        }
    )

    manifest_rows.append(
        {
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "subject_id": run["subject_id"],
            "session": run["session"],
            "anat_relpath": run["anat_relpath"],
            "local_path": str(local),
            "bytes": str(int(local.stat().st_size)),
            "sha256": sha256_file(local),
        }
    )

if qc_rows:
    status = "ok"
    reason = "computed"
    qc_rows.sort(key=lambda r: r["subject_id"])
else:
    status = "failed_precondition"
    reason = "no_usable_anatomical_images"
    qc_rows = [
        {
            "subject_id": "NA",
            "snr": "NA",
            "cnr": "NA",
            "qi1": "NA",
            "overall_rating": "fail",
            "status": status,
            "reason": reason,
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "method": "real_t1w_intensity_qc",
        }
    ]

out_csv = OUTPUT_DIR / "anatomical_qc.csv"
with out_csv.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "subject_id",
            "snr",
            "cnr",
            "qi1",
            "overall_rating",
            "status",
            "reason",
            "dataset_id",
            "snapshot_tag",
            "method",
        ],
    )
    writer.writeheader()
    writer.writerows(qc_rows)

manifest_path = OUTPUT_DIR / "input_manifest.csv"
with manifest_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "dataset_id",
            "snapshot_tag",
            "subject_id",
            "session",
            "anat_relpath",
            "local_path",
            "bytes",
            "sha256",
        ],
    )
    writer.writeheader()
    writer.writerows(manifest_rows)

manifest_sha = sha256_file(manifest_path)
rating_counts = {
    "pass": int(sum(1 for r in qc_rows if r["overall_rating"] == "pass")),
    "warn": int(sum(1 for r in qc_rows if r["overall_rating"] == "warn")),
    "fail": int(sum(1 for r in qc_rows if r["overall_rating"] == "fail")),
}

meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": status,
    "reason": reason,
    "snapshot_tag": snapshot_tag,
    "method": "real_t1w_intensity_qc",
    "processing_subject_count": int(len(processed_subjects)),
    "processing_run_count": int(len(manifest_rows)),
    "input_file_count": int(len(manifest_rows)),
    "input_bytes_total": int(sum(int(r["bytes"]) for r in manifest_rows)),
    "openneuro_queries": int(query_count),
    "download_error_count": int(len(errors)),
    "rating_counts": rating_counts,
    "records_count": 3,
    "bytes_total": int(out_csv.stat().st_size + manifest_path.stat().st_size),
    "hash_manifest_sha256": manifest_sha,
}
meta_path = OUTPUT_DIR / "run_metadata.json"
meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {out_csv}")
print(f"Wrote {manifest_path}")
print(f"status={status} reason={reason}")
print(f"processed_subjects={len(processed_subjects)} selected_runs={len(selected)}")
PY
