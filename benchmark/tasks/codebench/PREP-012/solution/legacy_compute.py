import csv
import json
import os
import re
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np
from sklearn.decomposition import PCA

TASK_ID = "PREP-012"
DATASET_ID = "ds000105"
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
        func_dir = next((x for x in sub_items if x.get("directory") and x.get("filename") == "func"), None)
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
        bold = bolds[0]
        rel = f"{sub['filename']}/func/{bold['filename']}"
        return {
            "snapshot_tag": snapshot_tag,
            "subject_id": sub["filename"],
            "bold": bold,
            "bold_relpath": rel,
            "query_count": query_count,
        }

    raise RuntimeError("No BOLD file found in ds000105")


picked = find_first_bold_file()
bold_path = CACHE_DIR / picked["bold_relpath"]
if not bold_path.exists():
    download(picked["bold"]["urls"][0], bold_path)

img = nib.load(str(bold_path))
data = np.asarray(img.get_fdata(), dtype=np.float32)
if data.ndim != 4 or data.shape[3] < 20:
    raise RuntimeError(f"Unexpected BOLD shape: {data.shape}")

nx, ny, nz, nt = data.shape
mean_img = np.mean(data, axis=3)
brain = mean_img > np.percentile(mean_img, 20)
if int(np.sum(brain)) < 200:
    raise RuntimeError("Brain mask too small")

brain_vals = mean_img[brain]
wm_thr = np.percentile(brain_vals, 80)
csf_thr = np.percentile(brain_vals, 30)
wm_mask = brain & (mean_img >= wm_thr)
csf_mask = brain & (mean_img <= csf_thr)
noise_mask = wm_mask | csf_mask
if int(np.sum(noise_mask)) < 200:
    raise RuntimeError("Noise mask too small for CompCor")

noise_ts = data[noise_mask, :].T.astype(np.float32)  # (T, N)
noise_ts -= np.mean(noise_ts, axis=0, keepdims=True)
noise_std = np.std(noise_ts, axis=0, keepdims=True)
noise_std[noise_std < 1e-6] = 1.0
noise_ts /= noise_std

n_comp = int(min(5, nt - 1, noise_ts.shape[1] - 1))
n_comp = max(n_comp, 3)
pca = PCA(n_components=n_comp, svd_solver="full", random_state=0)
components = pca.fit_transform(noise_ts).astype(np.float32)  # (T, C)
explained = pca.explained_variance_ratio_.astype(np.float32)

Y = data.reshape(-1, nt).T.astype(np.float32)  # (T, V)
D = np.column_stack([np.ones((nt, 1), dtype=np.float32), components])
P = D @ np.linalg.pinv(D)

clean = np.empty_like(Y, dtype=np.float32)
chunk = 20000
for start in range(0, Y.shape[1], chunk):
    end = min(start + chunk, Y.shape[1])
    block = Y[:, start:end]
    clean[:, start:end] = block - P @ block

clean_4d = clean.T.reshape(nx, ny, nz, nt)

clean_out = OUTPUT_DIR / "cleaned_bold.nii.gz"
comp_out = OUTPUT_DIR / "compcor_components.tsv"
nib.save(nib.Nifti1Image(clean_4d, img.affine, img.header), str(clean_out))

with comp_out.open("w", encoding="utf-8", newline="") as f:
    fieldnames = ["timepoint"] + [f"compcor_{i+1}" for i in range(n_comp)]
    writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
    writer.writeheader()
    for t in range(nt):
        row = {"timepoint": t}
        for i in range(n_comp):
            row[f"compcor_{i+1}"] = f"{float(components[t, i]):.8f}"
        writer.writerow(row)

meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "snapshot_tag": picked["snapshot_tag"],
    "subject_id": picked["subject_id"],
    "input_bold_relpath": picked["bold_relpath"],
    "shape": [int(nx), int(ny), int(nz), int(nt)],
    "noise_voxels": int(np.sum(noise_mask)),
    "n_components": int(n_comp),
    "explained_variance_ratio": [float(v) for v in explained],
    "openneuro_queries": int(picked["query_count"]),
    "records_count": 2,
    "bytes_total": int(clean_out.stat().st_size + comp_out.stat().st_size),
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {clean_out} and {comp_out}")
