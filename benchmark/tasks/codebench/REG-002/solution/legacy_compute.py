import json
import os
import re
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn import image

TASK_ID = "REG-002"
DATASET_ID = "ds002424"
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
    with urllib.request.urlopen(req, timeout=180) as resp, dest.open("wb") as f:
        f.write(resp.read())


def pick_subject_files():
    snapshot_tag, root_files = list_files(None)
    query_count = 1
    subjects = sorted(
        [f for f in root_files if f.get("directory") and re.fullmatch(r"sub-[A-Za-z0-9_-]+", str(f.get("filename")))],
        key=lambda x: str(x["filename"]),
    )

    for sub in subjects:
        _, sub_items = list_files(sub["key"])
        query_count += 1

        session_dirs = [x for x in sub_items if x.get("directory") and str(x.get("filename", "")).startswith("ses-")]
        if not session_dirs:
            session_dirs = [{"filename": "", "key": sub["key"], "directory": True}]

        for ses in sorted(session_dirs, key=lambda x: str(x["filename"])):
            if ses["key"] != sub["key"]:
                _, ses_items = list_files(ses["key"])
                query_count += 1
            else:
                ses_items = sub_items

            anat_dir = next((x for x in ses_items if x.get("directory") and x.get("filename") == "anat"), None)
            func_dir = next((x for x in ses_items if x.get("directory") and x.get("filename") == "func"), None)
            if anat_dir is None or func_dir is None:
                continue

            _, anat_items = list_files(anat_dir["key"])
            _, func_items = list_files(func_dir["key"])
            query_count += 2

            t1_file = next(
                (
                    f
                    for f in sorted(anat_items, key=lambda x: str(x["filename"]))
                    if (not f.get("directory")) and re.search(r"_T1w\.nii(\.gz)?$", str(f.get("filename"))) and (f.get("urls") or [])
                ),
                None,
            )
            bold_file = next(
                (
                    f
                    for f in sorted(func_items, key=lambda x: str(x["filename"]))
                    if (not f.get("directory")) and re.search(r"_bold\.nii(\.gz)?$", str(f.get("filename"))) and (f.get("urls") or [])
                ),
                None,
            )
            if t1_file and bold_file:
                return {
                    "snapshot_tag": snapshot_tag,
                    "subject_id": sub["filename"],
                    "session_id": ses["filename"] or "nosession",
                    "t1_file": t1_file,
                    "bold_file": bold_file,
                    "query_count": query_count,
                }

    raise RuntimeError("Could not find subject/session with both T1w and BOLD files")


picked = pick_subject_files()
subject_id = picked["subject_id"]
session_id = picked["session_id"]

rel_prefix = subject_id + (f"/{session_id}" if session_id != "nosession" else "")
t1_rel = f"{rel_prefix}/anat/{picked['t1_file']['filename']}"
bold_rel = f"{rel_prefix}/func/{picked['bold_file']['filename']}"

t1_path = CACHE_DIR / t1_rel
bold_path = CACHE_DIR / bold_rel
if not t1_path.exists():
    download(picked["t1_file"]["urls"][0], t1_path)
if not bold_path.exists():
    download(picked["bold_file"]["urls"][0], bold_path)

t1_img = nib.load(str(t1_path))
bold_img = nib.load(str(bold_path))

bold_data = np.asarray(bold_img.get_fdata(), dtype=np.float32)
if bold_data.ndim == 4:
    n_tp = int(bold_data.shape[3])
    bold_mean_data = np.mean(bold_data, axis=3).astype(np.float32)
elif bold_data.ndim == 3:
    n_tp = 1
    bold_mean_data = bold_data.astype(np.float32)
else:
    raise RuntimeError(f"Unexpected BOLD dims: {bold_data.shape}")

bold_mean_img = nib.Nifti1Image(bold_mean_data, bold_img.affine, bold_img.header)
coreg_img = image.resample_to_img(bold_mean_img, t1_img, interpolation="continuous")
coreg_data = np.asarray(coreg_img.get_fdata(), dtype=np.float32)

flirt_matrix = np.linalg.inv(t1_img.affine) @ bold_mean_img.affine

mat_out = OUTPUT_DIR / "flirt_matrix.mat"
coreg_out = OUTPUT_DIR / "coregistered_bold.nii.gz"
np.savetxt(mat_out, flirt_matrix, fmt="%.10f")
nib.save(nib.Nifti1Image(coreg_data, t1_img.affine, t1_img.header), str(coreg_out))

meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "snapshot_tag": picked["snapshot_tag"],
    "subject_id": subject_id,
    "session_id": session_id,
    "source_t1w_relpath": t1_rel,
    "source_bold_relpath": bold_rel,
    "bold_timepoints": n_tp,
    "t1_shape": [int(v) for v in t1_img.shape[:3]],
    "bold_mean_shape": [int(v) for v in bold_mean_data.shape],
    "coregistered_shape": [int(v) for v in coreg_data.shape],
    "matrix_det": float(np.linalg.det(flirt_matrix)),
    "matrix_trace": float(np.trace(flirt_matrix)),
    "openneuro_queries": int(picked["query_count"]),
    "records_count": 2,
    "bytes_total": int(mat_out.stat().st_size + coreg_out.stat().st_size),
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {mat_out} and {coreg_out}")
