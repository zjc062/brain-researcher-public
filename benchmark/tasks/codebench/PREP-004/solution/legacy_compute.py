import json
import os
import re
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy.ndimage import center_of_mass, shift

TASK_ID = "PREP-004"
DATASET_ID = "ds003592"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
CACHE_DIR = Path(os.environ["CACHE_DIR"])

if os.environ.get("ML_FORCE_FAIL", "0") == "1" or os.environ.get("PREP_FORCE_FAIL", "0") == "1":
    raise RuntimeError("forced_failure")


def post_graphql(query: str) -> dict:
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "brain_researcher_benchmark"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
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


def download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "brain_researcher_benchmark"})
    with urllib.request.urlopen(req, timeout=180) as resp, dest.open("wb") as f:
        f.write(resp.read())


def find_first_bold_file():
    snapshot_tag, root_files = list_files(None)
    query_count = 1
    subjects = sorted(
        [f for f in root_files if f.get("directory") and re.fullmatch(r"sub-[A-Za-z0-9_-]+", str(f.get("filename")))],
        key=lambda x: str(x["filename"]),
    )
    for sub in subjects:
        _, sub_items = list_files(sub["key"])
        query_count += 1
        ses_dirs = [x for x in sub_items if x.get("directory") and str(x.get("filename", "")).startswith("ses-")]
        if not ses_dirs:
            ses_dirs = [{"filename": "", "key": sub["key"], "directory": True}]

        for ses in sorted(ses_dirs, key=lambda x: str(x["filename"])):
            if ses["key"] != sub["key"]:
                _, ses_items = list_files(ses["key"])
                query_count += 1
            else:
                ses_items = sub_items

            func_dir = next((x for x in ses_items if x.get("directory") and x.get("filename") == "func"), None)
            if func_dir is None:
                continue
            _, func_items = list_files(func_dir["key"])
            query_count += 1

            bolds = [
                f
                for f in sorted(func_items, key=lambda x: str(x["filename"]))
                if (not f.get("directory")) and re.search(r"_bold\.nii(\.gz)?$", str(f.get("filename"))) and (f.get("urls") or [])
            ]
            if not bolds:
                continue

            # Prefer echo-1 if multi-echo files exist.
            preferred = None
            for b in bolds:
                if "echo-1" in str(b["filename"]):
                    preferred = b
                    break
            if preferred is None:
                preferred = bolds[0]

            ses_name = ses["filename"] or "nosession"
            rel_prefix = sub["filename"] + (f"/{ses_name}" if ses_name != "nosession" else "")
            rel = f"{rel_prefix}/func/{preferred['filename']}"
            return {
                "snapshot_tag": snapshot_tag,
                "subject_id": sub["filename"],
                "session_id": ses_name,
                "bold": preferred,
                "bold_relpath": rel,
                "query_count": query_count,
            }

    raise RuntimeError("No BOLD file found in ds003592")


picked = find_first_bold_file()
bold_path = CACHE_DIR / picked["bold_relpath"]
if not bold_path.exists():
    download(picked["bold"]["urls"][0], bold_path)

img = nib.load(str(bold_path))
data = np.asarray(img.get_fdata(), dtype=np.float32)
if data.ndim != 4 or data.shape[3] < 10:
    raise RuntimeError(f"Unexpected BOLD shape: {data.shape}")

nx, ny, nz, nt = data.shape
ref = data[..., 0]
ref_mask = ref > np.percentile(ref, 70)
if int(np.sum(ref_mask)) < 100:
    ref_mask = ref > np.percentile(ref, 50)
ref_com = np.asarray(center_of_mass(ref_mask.astype(np.float32)), dtype=np.float32)

corrected = np.empty_like(data, dtype=np.float32)
params = np.zeros((nt, 6), dtype=np.float32)

for t in range(nt):
    vol = data[..., t]
    mask = vol > np.percentile(vol, 70)
    if int(np.sum(mask)) < 100:
        mask = vol > np.percentile(vol, 50)
    com = np.asarray(center_of_mass(mask.astype(np.float32)), dtype=np.float32)
    if not np.isfinite(com).all():
        com = ref_com.copy()
    delta = ref_com - com

    corrected[..., t] = shift(vol, shift=tuple(float(v) for v in delta), order=1, mode="nearest")
    params[t, :3] = delta
    params[t, 3:] = 0.0

fd = np.zeros(nt, dtype=np.float32)
if nt > 1:
    fd[1:] = np.sum(np.abs(np.diff(params[:, :3], axis=0)), axis=1)

out_img = OUTPUT_DIR / "motion_corrected_bold.nii.gz"
out_txt = OUTPUT_DIR / "motion_parameters.txt"
nib.save(nib.Nifti1Image(corrected, img.affine, img.header), str(out_img))
np.savetxt(out_txt, params, fmt="%.6f")

meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "snapshot_tag": picked["snapshot_tag"],
    "subject_id": picked["subject_id"],
    "session_id": picked["session_id"],
    "input_bold_relpath": picked["bold_relpath"],
    "shape": [int(nx), int(ny), int(nz), int(nt)],
    "n_timepoints": int(nt),
    "mean_abs_translation": float(np.mean(np.abs(params[:, :3]))),
    "max_abs_translation": float(np.max(np.abs(params[:, :3]))),
    "mean_fd": float(np.mean(fd)),
    "openneuro_queries": int(picked["query_count"]),
    "records_count": 2,
    "bytes_total": int(out_img.stat().st_size + out_txt.stat().st_size),
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {out_img} and {out_txt}")
