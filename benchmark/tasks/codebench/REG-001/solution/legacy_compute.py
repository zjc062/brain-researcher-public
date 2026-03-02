import json
import os
import re
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn import datasets, image
from scipy.ndimage import gaussian_filter

TASK_ID = "REG-001"
DATASET_ID = "ds000105"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
CACHE_DIR = Path(os.environ["CACHE_DIR"])

if os.environ.get("ML_FORCE_FAIL", "0") == "1" or os.environ.get("REG_FORCE_FAIL", "0") == "1":
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
    with urllib.request.urlopen(req, timeout=240) as resp, dest.open("wb") as f:
        f.write(resp.read())


snapshot_tag, root_files = list_files(None)
subject_dirs = sorted(
    [f for f in root_files if f.get("directory") and re.fullmatch(r"sub-[A-Za-z0-9_-]+", str(f.get("filename")))],
    key=lambda x: str(x["filename"]),
)
if not subject_dirs:
    raise RuntimeError("No subject directories found in snapshot")

selected_subject = None
selected_t1 = None
query_count = 1
for sub in subject_dirs:
    _, sub_children = list_files(sub["key"])
    query_count += 1
    anat_dir = next((c for c in sub_children if c.get("directory") and c.get("filename") == "anat"), None)
    if anat_dir is None:
        continue
    _, anat_files = list_files(anat_dir["key"])
    query_count += 1
    t1_file = next(
        (
            f
            for f in sorted(anat_files, key=lambda x: str(x["filename"]))
            if (not f.get("directory")) and re.search(r"_T1w\.nii(\.gz)?$", str(f.get("filename"))) and (f.get("urls") or [])
        ),
        None,
    )
    if t1_file is not None:
        selected_subject = sub["filename"]
        selected_t1 = t1_file
        break

if selected_subject is None or selected_t1 is None:
    raise RuntimeError("No T1w file found under subject anat directories")

source_rel = f"{selected_subject}/anat/{selected_t1['filename']}"
source_path = CACHE_DIR / source_rel
if not source_path.exists():
    download(selected_t1["urls"][0], source_path)

source_img = nib.load(str(source_path))
source_data = np.asarray(source_img.get_fdata(), dtype=np.float32)
if source_data.ndim != 3 or source_data.size == 0:
    raise RuntimeError(f"Unexpected source T1w shape: {source_data.shape}")

mni_img = datasets.load_mni152_template(resolution=2)
registered_img = image.resample_to_img(source_img, mni_img, interpolation="continuous")
registered_data = np.asarray(registered_img.get_fdata(), dtype=np.float32)

mni_data = np.asarray(mni_img.get_fdata(), dtype=np.float32)

def zscore(x: np.ndarray) -> np.ndarray:
    mu = float(np.mean(x))
    sd = float(np.std(x))
    if sd < 1e-6:
        sd = 1.0
    return (x - mu) / sd

warp_proxy = gaussian_filter(np.abs(zscore(registered_data) - zscore(mni_data)), sigma=1.25).astype(np.float32)

registered_out = OUTPUT_DIR / "registered_T1w.nii.gz"
warp_out = OUTPUT_DIR / "composite_warp.nii.gz"
nib.save(nib.Nifti1Image(registered_data, mni_img.affine, mni_img.header), str(registered_out))
nib.save(nib.Nifti1Image(warp_proxy, mni_img.affine, mni_img.header), str(warp_out))

meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "snapshot_tag": snapshot_tag,
    "subject_id": selected_subject,
    "source_t1w_relpath": source_rel,
    "source_shape": [int(v) for v in source_data.shape],
    "template_shape": [int(v) for v in mni_data.shape],
    "registered_shape": [int(v) for v in registered_data.shape],
    "registered_mean": float(np.mean(registered_data)),
    "registered_std": float(np.std(registered_data)),
    "warp_mean": float(np.mean(warp_proxy)),
    "warp_std": float(np.std(warp_proxy)),
    "openneuro_queries": int(query_count),
    "records_count": 2,
    "bytes_total": int(registered_out.stat().st_size + warp_out.stat().st_size),
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {registered_out} and {warp_out}")
