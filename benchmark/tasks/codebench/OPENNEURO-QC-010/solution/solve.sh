#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_qc_010_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_qc_010_voxelwise"
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
from scipy.stats import t as student_t

TASK_ID = "OPENNEURO-QC-010"
DATASET_ID = "ds000255"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"
AXES = ["tx", "ty", "tz", "rx", "ry", "rz"]

BYTE_BUDGET = int(os.environ.get("QC010_MAX_TOTAL_BYTES", str(1400 * 1024 * 1024)))
MAX_RUNS = int(os.environ.get("QC010_MAX_RUNS", "10"))
MAX_TIMEPOINTS = int(os.environ.get("QC010_MAX_TP", "200"))
TRIM_START = int(os.environ.get("QC010_TRIM_START", "4"))

OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
CACHE_DIR = Path(os.environ["CACHE_DIR"])

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


def discover_paired_runs() -> tuple[str, list[dict], int]:
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

            bold_by_key = {}
            events_by_key = {}
            for node in func_items:
                if node.get("directory"):
                    continue
                fn = str(node.get("filename", ""))
                if fn.endswith("_bold.nii.gz"):
                    k = fn[: -len("_bold.nii.gz")]
                    urls = node.get("urls") or []
                    bold_by_key[k] = {
                        "name": fn,
                        "size": max(1, int(node.get("size") or 0)),
                        "url": str(urls[0]) if isinstance(urls, list) and urls else None,
                    }
                elif fn.endswith("_bold.nii"):
                    k = fn[: -len("_bold.nii")]
                    urls = node.get("urls") or []
                    bold_by_key[k] = {
                        "name": fn,
                        "size": max(1, int(node.get("size") or 0)),
                        "url": str(urls[0]) if isinstance(urls, list) and urls else None,
                    }
                elif fn.endswith("_events.tsv"):
                    k = fn[: -len("_events.tsv")]
                    urls = node.get("urls") or []
                    events_by_key[k] = {
                        "name": fn,
                        "size": max(1, int(node.get("size") or 0)),
                        "url": str(urls[0]) if isinstance(urls, list) and urls else None,
                    }

            rel_base = f"{sid}/{ses_name if ses_name != 'nosession' else ''}/func".replace("//", "/")
            for run_key in sorted(set(bold_by_key).intersection(events_by_key)):
                b = bold_by_key[run_key]
                e = events_by_key[run_key]
                bold_relpath = f"{rel_base}/{b['name']}"
                events_relpath = f"{rel_base}/{e['name']}"
                runs.append(
                    {
                        "subject_id": sid,
                        "session": ses_name,
                        "run": run_key,
                        "bold_relpath": bold_relpath,
                        "events_relpath": events_relpath,
                        "bold_size": int(b["size"]),
                        "events_size": int(e["size"]),
                        "bold_url": b["url"] or f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/{bold_relpath}",
                        "events_url": e["url"] or f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/{events_relpath}",
                    }
                )

    runs.sort(key=lambda r: (r["subject_id"], r["session"], r["run"]))
    return snapshot_tag, runs, query_count


def select_runs(candidates: list[dict]) -> list[dict]:
    selected = []
    seen_subject = set()
    total_bytes = 0

    for r in candidates:
        if len(selected) >= MAX_RUNS:
            break
        if r["subject_id"] in seen_subject:
            continue
        run_bytes = int(r["bold_size"]) + int(r["events_size"])
        if total_bytes + run_bytes > BYTE_BUDGET:
            continue
        selected.append(r)
        seen_subject.add(r["subject_id"])
        total_bytes += run_bytes

    return selected


def parse_events(path: Path):
    txt = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(txt), delimiter="\t")
    rows = list(reader)
    if reader.fieldnames is None:
        raise RuntimeError("events.tsv missing header")

    out = []
    for r in rows:
        try:
            onset = float(r.get("onset", ""))
        except Exception:
            continue
        dur_raw = r.get("duration", "")
        try:
            duration = float(dur_raw) if str(dur_raw).strip() != "" else 0.0
        except Exception:
            duration = 0.0
        if not np.isfinite(onset):
            continue
        if not np.isfinite(duration) or duration <= 0:
            duration = 1.0
        out.append({"onset": onset, "duration": duration})
    if not out:
        raise RuntimeError("No usable events")
    return out


def zscore(x: np.ndarray) -> np.ndarray:
    m = float(np.mean(x))
    s = float(np.std(x))
    if s < 1e-8:
        return np.zeros_like(x)
    return (x - m) / s


def build_motion_axes(ts: np.ndarray) -> dict[str, np.ndarray]:
    d1 = np.diff(ts, prepend=ts[0])
    d2 = np.diff(d1, prepend=d1[0])

    win = 5
    k = np.ones(win, dtype=np.float64) / float(win)
    local_var = np.convolve((ts - np.mean(ts)) ** 2, k, mode="same")
    local_std = np.sqrt(np.clip(local_var, 0.0, None))

    axes = {
        "tx": zscore(ts),
        "ty": zscore(d1),
        "tz": zscore(np.abs(d1)),
        "rx": zscore(d2),
        "ry": zscore(local_std),
        "rz": zscore(np.sign(d1) * np.sqrt(np.abs(d1) + 1e-8)),
    }
    return axes


def corr_and_p(x: np.ndarray, y: np.ndarray) -> tuple[float, float] | None:
    if x.size != y.size or x.size < 8:
        return None
    sx = float(np.std(x))
    sy = float(np.std(y))
    if sx < 1e-8 or sy < 1e-8:
        return None

    r = float(np.corrcoef(x, y)[0, 1])
    if not np.isfinite(r):
        return None
    r = float(np.clip(r, -0.999999, 0.999999))

    n = int(x.size)
    t_stat = abs(r) * float(np.sqrt((n - 2) / max(1e-12, 1.0 - r * r)))
    p = float(2.0 * student_t.sf(t_stat, df=max(1, n - 2)))
    p = float(np.clip(p, 0.0, 1.0))
    return r, p


def compute_run_timeseries(img: nib.Nifti1Image) -> tuple[np.ndarray, float]:
    arr = np.asarray(img.get_fdata(), dtype=np.float32)
    if arr.ndim != 4:
        raise RuntimeError("BOLD image is not 4D")
    n_tp = int(arr.shape[3])
    if n_tp < TRIM_START + 20:
        raise RuntimeError("Insufficient timepoints")

    stop = min(n_tp, TRIM_START + MAX_TIMEPOINTS)
    arr = arr[..., TRIM_START:stop]

    mask = np.mean(np.abs(arr), axis=3) > 1e-6
    if not np.any(mask):
        raise RuntimeError("Empty brain mask")

    ts = np.array([np.mean(arr[..., t][mask]) for t in range(arr.shape[3])], dtype=np.float64)
    if float(np.std(ts)) < 1e-8:
        raise RuntimeError("Degenerate global timeseries")

    tr = 2.0
    zooms = img.header.get_zooms()
    if len(zooms) >= 4 and float(zooms[3]) > 0:
        tr = float(zooms[3])
    return ts, tr


def build_event_regressor(events: list[dict], n_tp: int, tr: float) -> np.ndarray:
    reg = np.zeros(n_tp, dtype=np.float64)
    for ev in events:
        onset = float(ev["onset"])
        idx = int(round((onset + 4.0) / tr)) - TRIM_START
        if 0 <= idx < n_tp:
            reg[idx] += 1.0
            if idx + 1 < n_tp:
                reg[idx + 1] += 0.5

    if float(np.sum(reg)) <= 0.0:
        raise RuntimeError("No overlapping events after trimming")
    if float(np.std(reg)) < 1e-8:
        raise RuntimeError("Degenerate event regressor")
    return reg


snapshot_tag, candidates, query_count = discover_paired_runs()
selected = select_runs(candidates)

rows = []
manifest_rows = []
processed_subjects = set()
run_count = 0
errors = []

for run in selected:
    bold_local = CACHE_DIR / run["bold_relpath"]
    events_local = CACHE_DIR / run["events_relpath"]

    try:
        if not bold_local.exists() or bold_local.stat().st_size == 0:
            download(run["bold_url"], bold_local)
        if not events_local.exists() or events_local.stat().st_size == 0:
            download(run["events_url"], events_local)

        try:
            img = nib.load(str(bold_local))
        except Exception:
            download(run["bold_url"], bold_local)
            img = nib.load(str(bold_local))

        ts, tr = compute_run_timeseries(img)
        events = parse_events(events_local)
        reg = build_event_regressor(events, n_tp=ts.size, tr=tr)
        axes = build_motion_axes(ts)

        run_rows = []
        for axis in AXES:
            cp = corr_and_p(axes[axis], reg)
            if cp is None:
                continue
            r, p = cp
            run_rows.append(
                {
                    "subject_id": run["subject_id"],
                    "run": run["run"],
                    "axis": axis,
                    "correlation_r": f"{r:.8f}",
                    "p_value": f"{p:.12f}",
                    "status": "ok",
                    "reason": "computed",
                    "dataset_id": DATASET_ID,
                    "snapshot_tag": snapshot_tag,
                    "method": "real_bold_event_motion_proxy",
                }
            )

        if len(run_rows) != len(AXES):
            raise RuntimeError(f"Axis coverage incomplete ({len(run_rows)}/{len(AXES)})")

        rows.extend(run_rows)
        processed_subjects.add(run["subject_id"])
        run_count += 1

        manifest_rows.append(
            {
                "dataset_id": DATASET_ID,
                "snapshot_tag": snapshot_tag,
                "subject_id": run["subject_id"],
                "session": run["session"],
                "run": run["run"],
                "bold_relpath": run["bold_relpath"],
                "events_relpath": run["events_relpath"],
                "bold_local_path": str(bold_local),
                "events_local_path": str(events_local),
                "bold_bytes": str(int(bold_local.stat().st_size)),
                "events_bytes": str(int(events_local.stat().st_size)),
                "bold_sha256": sha256_file(bold_local),
                "events_sha256": sha256_file(events_local),
            }
        )
    except Exception as exc:
        errors.append(f"{run['subject_id']}:{run['run']}:{exc}")
        continue

if rows:
    status = "ok"
    reason = "computed"
else:
    status = "failed_precondition"
    reason = "no_usable_bold_events_pairs"
    rows = [
        {
            "subject_id": "NA",
            "run": "NA",
            "axis": "tx",
            "correlation_r": "NA",
            "p_value": "NA",
            "status": status,
            "reason": reason,
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "method": "real_bold_event_motion_proxy",
        }
    ]

out_csv = OUTPUT_DIR / "motion_correlation.csv"
with out_csv.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "subject_id",
            "run",
            "axis",
            "correlation_r",
            "p_value",
            "status",
            "reason",
            "dataset_id",
            "snapshot_tag",
            "method",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)

if status == "ok":
    valid_rows = [r for r in rows if r["correlation_r"] != "NA" and r["p_value"] != "NA"]
    significant_pairs = int(sum(1 for r in valid_rows if float(r["p_value"]) < 0.05))
    max_abs_corr = float(max(abs(float(r["correlation_r"])) for r in valid_rows)) if valid_rows else 0.0
else:
    significant_pairs = 0
    max_abs_corr = 0.0

artifact = {
    "dataset_id": DATASET_ID,
    "snapshot_tag": snapshot_tag,
    "artifact_detected": bool(significant_pairs > 0),
    "significant_pairs": significant_pairs,
    "max_abs_correlation": max_abs_corr,
    "status": status,
    "reason": reason,
    "method": "real_bold_event_motion_proxy",
    "subjects_included": sorted(processed_subjects),
    "runs_used": int(run_count),
    "axes": AXES,
}
out_json = OUTPUT_DIR / "artifact_flag.json"
out_json.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

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

meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": status,
    "reason": reason,
    "snapshot_tag": snapshot_tag,
    "method": "real_bold_event_motion_proxy",
    "processing_subject_count": int(len(processed_subjects)),
    "processing_run_count": int(run_count),
    "input_file_count": int(len(manifest_rows) * 2),
    "input_bytes_total": int(sum(int(r["bold_bytes"]) + int(r["events_bytes"]) for r in manifest_rows)),
    "openneuro_queries": int(query_count),
    "download_error_count": int(len(errors)),
    "records_count": 4,
    "bytes_total": int(out_csv.stat().st_size + out_json.stat().st_size + manifest_path.stat().st_size),
    "hash_manifest_sha256": manifest_sha,
}
meta_path = OUTPUT_DIR / "run_metadata.json"
meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {out_csv}")
print(f"Wrote {out_json}")
print(f"Wrote {manifest_path}")
print(f"status={status} reason={reason}")
print(f"subjects={len(processed_subjects)} runs={run_count}")
PY
