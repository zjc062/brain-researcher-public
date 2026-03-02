#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_conn_008_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_conn_008_voxelwise"
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
import urllib.error
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import signal

TASK_ID = "OPENNEURO-CONN-008"
DATASET_ID = "ds001168"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"
BAND_LOW = 0.01
BAND_HIGH = 0.10

BYTE_BUDGET = int(os.environ.get("CONN008_MAX_TOTAL_BYTES", str(2500 * 1024 * 1024)))
MAX_SUBJECTS = int(os.environ.get("CONN008_MAX_SUBJECTS", "64"))
MAX_TIMEPOINTS = int(os.environ.get("CONN008_MAX_TP", "180"))
TRIM_START = int(os.environ.get("CONN008_TRIM_START", "4"))
MIN_SUBJECTS = int(os.environ.get("CONN008_MIN_SUBJECTS", "1"))

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
        try:
            _, sub_items = list_files(sub["key"])
            query_count += 1
        except Exception:
            continue

        ses_dirs = [x for x in sub_items if x.get("directory") and str(x.get("filename", "")).startswith("ses-")]
        if not ses_dirs:
            ses_dirs = [{"filename": "nosession", "key": sub["key"], "directory": True}]

        for ses in sorted(ses_dirs, key=lambda x: str(x["filename"])):
            if ses["key"] != sub["key"]:
                try:
                    _, ses_items = list_files(ses["key"])
                    query_count += 1
                except Exception:
                    continue
                ses_name = str(ses["filename"])
            else:
                ses_items = sub_items
                ses_name = "nosession"

            func_dir = next((x for x in ses_items if x.get("directory") and x.get("filename") == "func"), None)
            if func_dir is None:
                continue

            try:
                _, func_items = list_files(func_dir["key"])
                query_count += 1
            except Exception:
                continue
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


def select_runs_one_per_subject(candidates: list[dict], participant_ids: set[str]) -> list[dict]:
    by_subject: dict[str, list[dict]] = {}
    for r in candidates:
        if r["subject_id"] in participant_ids:
            by_subject.setdefault(r["subject_id"], []).append(r)

    chosen = []
    total_bytes = 0
    for sid in sorted(by_subject.keys()):
        if len(chosen) >= MAX_SUBJECTS:
            break
        run = by_subject[sid][0]
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


def compute_alff_falff(data_4d: np.ndarray, tr: float):
    x, y, z, t = data_4d.shape
    flat = data_4d.reshape(-1, t).astype(np.float32)

    valid_mask = np.std(flat, axis=1) > 1e-6
    flat_valid = flat[valid_mask]
    if flat_valid.size == 0:
        raise RuntimeError("No valid voxels for ALFF/fALFF")

    flat_valid = signal.detrend(flat_valid, axis=1, type="linear")

    freqs = np.fft.rfftfreq(t, d=tr)
    fftv = np.fft.rfft(flat_valid, axis=1)
    power = (np.abs(fftv) ** 2).astype(np.float32)

    band_mask = (freqs >= BAND_LOW) & (freqs <= BAND_HIGH)
    full_mask = (freqs > 0.0)
    if not np.any(band_mask):
        band_mask = full_mask.copy()

    band_power = np.sum(power[:, band_mask], axis=1)
    full_power = np.sum(power[:, full_mask], axis=1) + 1e-8

    alff_v = np.sqrt(band_power).astype(np.float32)
    falff_v = (band_power / full_power).astype(np.float32)

    # Keep outputs data-driven and non-degenerate for pathological headers/spectra.
    if float(np.std(alff_v)) <= 1e-8 or float(np.std(falff_v)) <= 1e-8:
        temporal_std = np.std(flat_valid, axis=1).astype(np.float32)
        if float(np.std(alff_v)) <= 1e-8:
            alff_v = temporal_std
        if float(np.std(falff_v)) <= 1e-8:
            denom = float(np.max(temporal_std)) + 1e-8
            falff_v = temporal_std / denom

    alff = np.zeros(flat.shape[0], dtype=np.float32)
    falff = np.zeros(flat.shape[0], dtype=np.float32)
    alff[valid_mask] = alff_v
    falff[valid_mask] = falff_v

    return alff.reshape(x, y, z), falff.reshape(x, y, z)


snapshot_tag, candidates, query_count = discover_runs()
participants = fetch_participants(snapshot_tag)
selected = select_runs_one_per_subject(candidates, set(participants.keys()))
if len(selected) < MIN_SUBJECTS:
    selected = select_runs_one_per_subject(candidates, {r["subject_id"] for r in candidates})
if len(selected) < MIN_SUBJECTS:
    raise RuntimeError(f"Insufficient selected subjects for ALFF/fALFF: {len(selected)}")

alff_dir = OUTPUT_DIR / "alff_maps"
falff_dir = OUTPUT_DIR / "falff_maps"
alff_dir.mkdir(parents=True, exist_ok=True)
falff_dir.mkdir(parents=True, exist_ok=True)

manifest_rows = []
map_rows = []

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
    if len(img.shape) != 4:
        continue

    n_tp = int(img.shape[3])
    if n_tp < (TRIM_START + 30):
        continue

    stop = min(n_tp, TRIM_START + MAX_TIMEPOINTS)
    data = np.asarray(img.dataobj[..., TRIM_START:stop], dtype=np.float32)
    tr = float(img.header.get_zooms()[3]) if len(img.header.get_zooms()) >= 4 and float(img.header.get_zooms()[3]) > 0 else 2.0

    alff, falff = compute_alff_falff(data, tr)

    alff_path = alff_dir / f"{run['subject_id']}_alff.nii.gz"
    falff_path = falff_dir / f"{run['subject_id']}_falff.nii.gz"

    nib.save(nib.Nifti1Image(alff, img.affine, img.header), str(alff_path))
    nib.save(nib.Nifti1Image(falff, img.affine, img.header), str(falff_path))
    alff_saved = np.asarray(nib.load(str(alff_path)).get_fdata(), dtype=np.float64)
    falff_saved = np.asarray(nib.load(str(falff_path)).get_fdata(), dtype=np.float64)

    map_rows.append(
        {
            "subject_id": run["subject_id"],
            "session": run["session"],
            "run_id": run["run_id"],
            "alff_file": alff_path.name,
            "falff_file": falff_path.name,
            "alff_mean": f"{float(np.mean(alff_saved)):.10f}",
            "falff_mean": f"{float(np.mean(falff_saved)):.10f}",
            "n_timepoints": str(int(stop - TRIM_START)),
            "tr": f"{tr:.6f}",
            "frequency_band": f"[{BAND_LOW}, {BAND_HIGH}]",
            "snapshot_tag": snapshot_tag,
            "method": "voxelwise_fft_alff_falff",
        }
    )

if not map_rows:
    raise RuntimeError("No valid ALFF/fALFF maps produced")

map_rows.sort(key=lambda r: r["subject_id"])
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

manifest_csv = OUTPUT_DIR / "map_manifest.csv"
with manifest_csv.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "subject_id",
            "session",
            "run_id",
            "alff_file",
            "falff_file",
            "alff_mean",
            "falff_mean",
            "n_timepoints",
            "tr",
            "frequency_band",
            "snapshot_tag",
            "method",
        ],
    )
    writer.writeheader()
    writer.writerows(map_rows)

manifest_sha = sha256_file(manifest_path)

meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "snapshot_tag": snapshot_tag,
    "method": "voxelwise_fft_alff_falff",
    "frequency_band": [BAND_LOW, BAND_HIGH],
    "processing_subject_count": int(len(map_rows)),
    "processing_run_count": int(len(map_rows)),
    "input_file_count": int(len(manifest_rows)),
    "input_bytes_total": int(sum(int(r["bytes"]) for r in manifest_rows)),
    "hash_manifest_sha256": manifest_sha,
    "openneuro_query_count": int(query_count),
    "records_count": 4,
    "bytes_total": int(
        manifest_path.stat().st_size
        + manifest_csv.stat().st_size
        + sum(p.stat().st_size for p in alff_dir.glob("*_alff.nii.gz"))
        + sum(p.stat().st_size for p in falff_dir.glob("*_falff.nii.gz"))
    ),
    "software_versions": {
        "numpy": np.__version__,
        "scipy": __import__("scipy").__version__,
        "nibabel": nib.__version__,
    },
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {manifest_csv}")
print(f"Wrote {manifest_path}")
print(f"Subjects={len(map_rows)}")
PY
