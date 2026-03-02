#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_sa_007_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_sa_007_voxelwise"
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

TASK_ID = "OPENNEURO-SA-007"
DATASET_ID = "ds000255"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

BYTE_BUDGET = int(os.environ.get("SA007_MAX_TOTAL_BYTES", str(1200 * 1024 * 1024)))
MAX_RUNS = int(os.environ.get("SA007_MAX_RUNS", "12"))
MAX_TIMEPOINTS = int(os.environ.get("SA007_MAX_TP", "160"))
TRIM_START = int(os.environ.get("SA007_TRIM_START", "4"))
MIN_EVENT_SAMPLES = int(os.environ.get("SA007_MIN_EVENT_SAMPLES", "3"))

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


def fetch_participants(snapshot_tag: str) -> set[str]:
    url = f"https://openneuro.org/crn/datasets/{DATASET_ID}/snapshots/{snapshot_tag}/files/participants.tsv"
    req = urllib.request.Request(url, headers={"User-Agent": "brain_researcher_benchmark"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            txt = resp.read().decode("utf-8")
    except Exception:
        return set()
    reader = csv.DictReader(io.StringIO(txt), delimiter="\t")
    rows = list(reader)
    if reader.fieldnames is None or "participant_id" not in reader.fieldnames:
        return set()
    return {str(r["participant_id"]).strip() for r in rows if r.get("participant_id")}


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
            for f in sorted(func_items, key=lambda x: str(x.get("filename", ""))):
                if f.get("directory"):
                    continue
                name = str(f.get("filename", ""))
                size = int(f.get("size") or 0)
                if name.endswith("_bold.nii.gz"):
                    key = name[: -len("_bold.nii.gz")]
                    bold_by_key[key] = {"name": name, "size": size}
                elif name.endswith("_bold.nii"):
                    key = name[: -len("_bold.nii")]
                    bold_by_key[key] = {"name": name, "size": size}
                elif name.endswith("_events.tsv"):
                    key = name[: -len("_events.tsv")]
                    events_by_key[key] = {"name": name, "size": size}

            for key in sorted(set(bold_by_key).intersection(events_by_key)):
                bold = bold_by_key[key]
                events = events_by_key[key]
                rel_base = f"{sid}/{ses_name if ses_name != 'nosession' else ''}/func".replace("//", "/")
                bold_rel = f"{rel_base}/{bold['name']}"
                events_rel = f"{rel_base}/{events['name']}"
                runs.append(
                    {
                        "subject_id": sid,
                        "session": ses_name,
                        "run": key,
                        "bold_relpath": bold_rel,
                        "events_relpath": events_rel,
                        "bold_size": max(1, int(bold["size"])),
                        "events_size": max(1, int(events["size"])),
                        "bold_url": f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/{bold_rel}",
                        "events_url": f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/{events_rel}",
                    }
                )

    runs.sort(key=lambda r: (r["subject_id"], r["session"], r["run"]))
    return snapshot_tag, runs, query_count


def select_runs(candidates: list[dict], participant_ids: set[str]) -> list[dict]:
    by_subject: dict[str, list[dict]] = {}
    for r in candidates:
        if participant_ids and r["subject_id"] not in participant_ids:
            continue
        by_subject.setdefault(r["subject_id"], []).append(r)

    chosen = []
    total_bytes = 0

    for sid in sorted(by_subject.keys()):
        if len(chosen) >= MAX_RUNS:
            break
        run = by_subject[sid][0]
        size = int(run["bold_size"]) + int(run["events_size"])
        if total_bytes + size > BYTE_BUDGET:
            continue
        chosen.append(run)
        total_bytes += size

    extras = []
    for sid in sorted(by_subject.keys()):
        extras.extend(by_subject[sid][1:])
    for run in extras:
        if len(chosen) >= MAX_RUNS:
            break
        size = int(run["bold_size"]) + int(run["events_size"])
        if total_bytes + size > BYTE_BUDGET:
            continue
        chosen.append(run)
        total_bytes += size

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


def parse_events(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        txt = f.read()
    reader = csv.DictReader(io.StringIO(txt), delimiter="\t")
    rows = list(reader)
    if reader.fieldnames is None:
        return []

    stim_col = None
    for c in ["trial_type", "stimulus_id", "stimulus", "condition", "event_type"]:
        if c in reader.fieldnames:
            stim_col = c
            break
    if stim_col is None:
        return []

    out = []
    for r in rows:
        onset_s = r.get("onset")
        dur_s = r.get("duration")
        stim = str(r.get(stim_col, "")).strip()
        if not stim:
            continue
        try:
            onset = float(onset_s)
        except Exception:
            continue
        try:
            duration = float(dur_s)
        except Exception:
            duration = 0.0
        if not np.isfinite(onset):
            continue
        if not np.isfinite(duration) or duration < 0:
            duration = 0.0
        out.append({"stimulus": stim, "onset": onset, "duration": duration})
    return out


def global_timeseries(img: nib.Nifti1Image, trim_start: int, max_tp: int) -> tuple[np.ndarray, float]:
    if len(img.shape) != 4:
        raise RuntimeError("BOLD image is not 4D")
    n_tp = int(img.shape[3])
    if n_tp < trim_start + 20:
        raise RuntimeError("Insufficient timepoints")
    stop = min(n_tp, trim_start + max_tp)
    data = np.asarray(img.dataobj[..., trim_start:stop], dtype=np.float32)
    t = int(data.shape[3])
    flat = data.reshape(-1, t)
    valid = np.std(flat, axis=1) > 1e-6
    if not np.any(valid):
        raise RuntimeError("No valid voxels")
    series = np.mean(flat[valid], axis=0).astype(np.float64)
    series = series - float(np.mean(series))
    tr = 2.0
    zooms = img.header.get_zooms()
    if len(zooms) >= 4 and float(zooms[3]) > 0:
        tr = float(zooms[3])
    return series, tr


def cohens_d_and_ci(samples: np.ndarray) -> tuple[float, float, float]:
    n = int(samples.size)
    mean = float(np.mean(samples))
    if n < 2:
        return 0.0, 0.0, 0.0
    sd = float(np.std(samples, ddof=1))
    if sd <= 1e-12:
        d = 0.0
    else:
        d = mean / sd
    if n <= 2:
        return d, d, d
    se = float(np.sqrt((1.0 / n) + ((d * d) / (2.0 * (n - 1)))))
    ci_low = d - 1.96 * se
    ci_high = d + 1.96 * se
    return d, ci_low, ci_high


snapshot_tag, candidates, query_count = discover_paired_runs()
participants = fetch_participants(snapshot_tag)
selected = select_runs(candidates, participants)

manifest_rows = []
stim_to_effects: dict[str, list[float]] = {}
processed_subjects = set()
processed_runs = 0
events_used = 0

for run in selected:
    bold_local = CACHE_DIR / run["bold_relpath"]
    events_local = CACHE_DIR / run["events_relpath"]
    if not bold_local.exists() or bold_local.stat().st_size == 0:
        download(run["bold_url"], bold_local)
    if not events_local.exists() or events_local.stat().st_size == 0:
        download(run["events_url"], events_local)

    try:
        img = nib.load(str(bold_local))
    except Exception:
        download(run["bold_url"], bold_local)
        img = nib.load(str(bold_local))

    events = parse_events(events_local)
    if not events:
        continue

    try:
        series, tr = global_timeseries(img, TRIM_START, MAX_TIMEPOINTS)
    except Exception:
        continue

    t_len = int(series.size)
    run_event_count = 0
    for ev in events:
        stim = ev["stimulus"]
        onset = float(ev["onset"])
        duration = float(ev["duration"])

        idx0 = int(round(onset / tr)) - TRIM_START
        hrf_shift = max(1, int(round(4.0 / tr)))
        ev_len = max(1, int(round(max(duration, tr) / tr)))

        baseline_a = max(0, idx0 - max(2, int(round(6.0 / tr))))
        baseline_b = max(0, min(t_len, idx0))
        resp_a = max(0, min(t_len, idx0 + hrf_shift))
        resp_b = max(0, min(t_len, resp_a + ev_len))

        if baseline_b - baseline_a < 2 or resp_b - resp_a < 1:
            continue

        baseline = float(np.mean(series[baseline_a:baseline_b]))
        response = float(np.mean(series[resp_a:resp_b]))
        effect = response - baseline
        if not np.isfinite(effect):
            continue

        stim_to_effects.setdefault(stim, []).append(effect)
        run_event_count += 1

    if run_event_count == 0:
        continue

    processed_subjects.add(run["subject_id"])
    processed_runs += 1
    events_used += run_event_count

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

reasons = []
if processed_runs < 1:
    reasons.append("paired_runs<1")
if events_used < MIN_EVENT_SAMPLES:
    reasons.append(f"event_samples<{MIN_EVENT_SAMPLES}")
if not stim_to_effects:
    reasons.append("stimuli_without_effects")

status = "failed_precondition" if reasons else "ok"
reason = ";".join(reasons) if reasons else "computed"

rows = []
if status == "ok":
    for stim, vals in sorted(stim_to_effects.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        arr = np.asarray(vals, dtype=np.float64)
        if arr.size < MIN_EVENT_SAMPLES:
            continue
        d, ci_low, ci_high = cohens_d_and_ci(arr)
        rows.append(
            {
                "stimulus_id": stim,
                "cohens_d": f"{d:.8f}",
                "ci_lower": f"{ci_low:.8f}",
                "ci_upper": f"{ci_high:.8f}",
                "n_samples": str(int(arr.size)),
                "mean_effect": f"{float(np.mean(arr)):.8f}",
                "status": status,
                "reason": reason,
                "subjects_included": str(len(processed_subjects)),
                "runs_used": str(processed_runs),
                "events_used": str(events_used),
                "dataset_id": DATASET_ID,
                "snapshot_tag": snapshot_tag,
                "method": "real_bold_event_effect_size",
            }
        )

if not rows:
    status = "failed_precondition"
    if not reasons:
        reason = f"event_samples<{MIN_EVENT_SAMPLES}"
    rows = [
        {
            "stimulus_id": "ALL",
            "cohens_d": "NA",
            "ci_lower": "NA",
            "ci_upper": "NA",
            "n_samples": "0",
            "mean_effect": "NA",
            "status": status,
            "reason": reason,
            "subjects_included": str(len(processed_subjects)),
            "runs_used": str(processed_runs),
            "events_used": str(events_used),
            "dataset_id": DATASET_ID,
            "snapshot_tag": snapshot_tag,
            "method": "real_bold_event_effect_size",
        }
    ]

rows.sort(key=lambda r: (r["stimulus_id"] != "ALL", r["stimulus_id"]))

out_csv = OUTPUT_DIR / "effect_sizes.csv"
with out_csv.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "stimulus_id",
            "cohens_d",
            "ci_lower",
            "ci_upper",
            "n_samples",
            "mean_effect",
            "status",
            "reason",
            "subjects_included",
            "runs_used",
            "events_used",
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
bytes_total = int(out_csv.stat().st_size + manifest_path.stat().st_size)
meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": status,
    "reason": reason,
    "snapshot_tag": snapshot_tag,
    "method": "real_bold_event_effect_size",
    "processing_subject_count": int(len(processed_subjects)),
    "processing_run_count": int(processed_runs),
    "events_used": int(events_used),
    "stimulus_count": int(sum(1 for r in rows if r["stimulus_id"] != "ALL")),
    "input_file_count": int(len(manifest_rows) * 2),
    "input_bytes_total": int(
        sum(int(r["bold_bytes"]) + int(r["events_bytes"]) for r in manifest_rows)
    ),
    "openneuro_queries": int(query_count),
    "records_count": 2,
    "bytes_total": int(bytes_total),
    "hash_manifest_sha256": manifest_sha,
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {out_csv}")
print(f"Wrote {manifest_path}")
print(f"status={status} reason={reason}")
print(f"Subjects={len(processed_subjects)} Runs={processed_runs} Events={events_used}")
PY
