import csv
import json
import os
import re
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy.ndimage import gaussian_filter
from sklearn.decomposition import FastICA

TASK_ID = "PREP-002"
DATASET_ID = "ds002424"
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

            bold = bolds[0]
            ses_name = ses["filename"] or "nosession"
            rel_prefix = sub["filename"] + (f"/{ses_name}" if ses_name != "nosession" else "")
            rel = f"{rel_prefix}/func/{bold['filename']}"
            return {
                "snapshot_tag": snapshot_tag,
                "subject_id": sub["filename"],
                "session_id": ses_name,
                "bold": bold,
                "bold_relpath": rel,
                "query_count": query_count,
            }

    raise RuntimeError("No BOLD file found in ds002424")


picked = find_first_bold_file()
bold_path = CACHE_DIR / picked["bold_relpath"]
if not bold_path.exists():
    download(picked["bold"]["urls"][0], bold_path)

bold_img = nib.load(str(bold_path))
data = np.asarray(bold_img.get_fdata(), dtype=np.float32)
if data.ndim != 4 or data.shape[3] < 20:
    raise RuntimeError(f"Unexpected BOLD shape: {data.shape}")

nx, ny, nz, nt = data.shape
tr = float(bold_img.header.get_zooms()[3]) if len(bold_img.header.get_zooms()) >= 4 else 1.0
if not np.isfinite(tr) or tr <= 0:
    tr = 1.0

# Build a reduced feature matrix for ICA component estimation.
reduced = data[::2, ::2, ::2, :]
X = reduced.reshape(-1, nt).T
X = X[:, np.var(X, axis=0) > 1e-6]
if X.shape[1] < 200:
    X = data.reshape(-1, nt).T
    X = X[:, np.var(X, axis=0) > 1e-6]
if X.shape[1] < 50:
    raise RuntimeError("Insufficient varying voxels for ICA")

# Deterministically cap voxels to keep runtime bounded.
if X.shape[1] > 5000:
    vars_ = np.var(X, axis=0)
    keep = np.argsort(vars_)[-5000:]
    X = X[:, keep]

X = X - np.mean(X, axis=0, keepdims=True)
std = np.std(X, axis=0, keepdims=True)
std[std < 1e-6] = 1.0
Xz = X / std

n_comp = int(min(20, nt - 1, Xz.shape[1] - 1))
n_comp = max(n_comp, 3)
ica = FastICA(n_components=n_comp, random_state=0, whiten="unit-variance", max_iter=500)
S = ica.fit_transform(Xz)  # (T, C)

# ICA-AROMA-style motion heuristics.
freqs = np.fft.rfftfreq(nt, d=tr)
pow_spec = np.abs(np.fft.rfft(S, axis=0)) ** 2
hf_mask = freqs >= 0.10
hf_ratio = np.sum(pow_spec[hf_mask, :], axis=0) / (np.sum(pow_spec[1:, :], axis=0) + 1e-12)

global_ts = np.mean(Xz, axis=1)
fd_proxy = np.r_[0.0, np.abs(np.diff(global_ts))]
fd_std = float(np.std(fd_proxy))
if fd_std < 1e-8:
    fd_std = 1.0
fd_proxy = (fd_proxy - np.mean(fd_proxy)) / fd_std

corrs = []
for i in range(n_comp):
    c = S[:, i]
    c = (c - np.mean(c)) / (np.std(c) + 1e-8)
    corrs.append(float(abs(np.corrcoef(c, fd_proxy)[0, 1])))
corrs = np.asarray(corrs, dtype=float)

motion_mask = (hf_ratio > 0.35) | (corrs > 0.35)
if int(np.sum(motion_mask)) == 0:
    motion_mask[int(np.argmax(corrs))] = True
motion_idx = np.where(motion_mask)[0]

# Non-aggressive denoising by regressing motion components from full voxel data.
Y = data.reshape(-1, nt).T.astype(np.float32)  # (T, V)
N = S[:, motion_idx]
N = np.column_stack([np.ones((nt, 1), dtype=np.float32), N.astype(np.float32)])
P = N @ np.linalg.pinv(N)

clean = np.empty_like(Y, dtype=np.float32)
chunk = 20000
for start in range(0, Y.shape[1], chunk):
    end = min(start + chunk, Y.shape[1])
    block = Y[:, start:end]
    clean[:, start:end] = block - P @ block

clean_4d = clean.T.reshape(nx, ny, nz, nt)
clean_4d = gaussian_filter(clean_4d, sigma=(0.6, 0.6, 0.6, 0.0)).astype(np.float32)

base_name = picked["bold"]["filename"]
out_name = re.sub(r"_bold\.nii(\.gz)?$", "_desc-smoothAROMAnonaggr_bold.nii.gz", base_name)
if out_name == base_name:
    out_name = "sub-01_desc-smoothAROMAnonaggr_bold.nii.gz"
out_img = OUTPUT_DIR / out_name
nib.save(nib.Nifti1Image(clean_4d, bold_img.affine, bold_img.header), str(out_img))

mix_tsv = OUTPUT_DIR / "mixing_matrix.tsv"
with mix_tsv.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["component_id", "variance_explained", "hf_ratio", "motion_corr", "is_motion", "n_timepoints"],
        delimiter="\t",
    )
    writer.writeheader()
    var_comp = np.var(S, axis=0)
    var_total = float(np.sum(var_comp)) + 1e-12
    for i in range(n_comp):
        writer.writerow(
            {
                "component_id": i + 1,
                "variance_explained": f"{float(var_comp[i] / var_total):.8f}",
                "hf_ratio": f"{float(hf_ratio[i]):.8f}",
                "motion_corr": f"{float(corrs[i]):.8f}",
                "is_motion": int(i in motion_idx),
                "n_timepoints": nt,
            }
        )

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
    "output_bold_file": out_name,
    "shape": [int(nx), int(ny), int(nz), int(nt)],
    "tr": float(tr),
    "n_components": int(n_comp),
    "n_motion_components": int(len(motion_idx)),
    "openneuro_queries": int(picked["query_count"]),
    "records_count": 2,
    "bytes_total": int(out_img.stat().st_size + mix_tsv.stat().st_size),
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {out_img} and {mix_tsv}")
