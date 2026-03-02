import json
import os
import re
import urllib.request
from pathlib import Path

import nibabel as nib
import numpy as np

TASK_ID = "PREP-010"
DATASET_ID = "ds000216"
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


def find_echo_group():
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

            echo_files = []
            for f in sorted(func_items, key=lambda x: str(x["filename"])):
                if f.get("directory"):
                    continue
                m = re.search(r"_echo-(\d+)_bold\.nii(\.gz)?$", str(f.get("filename")))
                if m and (f.get("urls") or []):
                    echo_files.append((f, int(m.group(1))))
            if len(echo_files) < 2:
                continue

            groups: dict[str, list[tuple[dict, int]]] = {}
            for f, idx in echo_files:
                key = re.sub(r"_echo-\d+_bold\.nii(\.gz)?$", "_echo-X_bold.nii.gz", str(f["filename"]))
                groups.setdefault(key, []).append((f, idx))

            candidates = [(k, v) for k, v in groups.items() if len(v) >= 2]
            if not candidates:
                continue
            candidates.sort(key=lambda kv: (-len(kv[1]), kv[0]))
            run_key, files = candidates[0]
            files = sorted(files, key=lambda x: x[1])

            ses_name = ses["filename"] or "nosession"
            rel_prefix = sub["filename"] + (f"/{ses_name}" if ses_name != "nosession" else "")
            rels = [f"{rel_prefix}/func/{f['filename']}" for f, _ in files]

            return {
                "snapshot_tag": snapshot_tag,
                "subject_id": sub["filename"],
                "session_id": ses_name,
                "run_key": run_key,
                "files": files,
                "rels": rels,
                "query_count": query_count,
            }

    raise RuntimeError("No multi-echo run with >=2 echoes found")


picked = find_echo_group()
local_paths = []
for rel, (f, _) in zip(picked["rels"], picked["files"]):
    p = CACHE_DIR / rel
    if not p.exists():
        download(f["urls"][0], p)
    local_paths.append(p)

imgs = [nib.load(str(p)) for p in local_paths]
arrs = [np.asarray(img.get_fdata(), dtype=np.float32) for img in imgs]

shape = arrs[0].shape
if any(a.shape != shape for a in arrs):
    raise RuntimeError("Echo images do not share the same shape")
if len(shape) != 4 or shape[3] < 5:
    raise RuntimeError(f"Unexpected multi-echo BOLD shape: {shape}")

echo_indices = [idx for _, idx in picked["files"]]
te_sec = np.asarray([0.012 * float(i) for i in echo_indices], dtype=np.float32)
weights = te_sec / float(np.sum(te_sec))

combined = np.zeros(shape, dtype=np.float32)
mean_echoes = []
for w, arr in zip(weights, arrs):
    combined += float(w) * arr
    mean_echoes.append(np.mean(arr, axis=3).astype(np.float32))

# Estimate T2* from per-echo mean signal using log-linear fit.
E = len(mean_echoes)
S = np.stack(mean_echoes, axis=-1)  # (X,Y,Z,E)
S = np.clip(S, 1e-6, None)
Y = np.log(S)
X = te_sec.reshape(1, 1, 1, E)

sum_x = float(np.sum(te_sec))
sum_x2 = float(np.sum(te_sec * te_sec))
sum_y = np.sum(Y, axis=3)
sum_xy = np.sum(X * Y, axis=3)
den = E * sum_x2 - sum_x * sum_x
slope = (E * sum_xy - sum_x * sum_y) / (den + 1e-12)

t2star = np.zeros_like(slope, dtype=np.float32)
valid = slope < -1e-6
t2star[valid] = (-1.0 / slope[valid]).astype(np.float32)
t2star = np.clip(t2star, 0.0, 0.200)

combined_out = OUTPUT_DIR / "combined_bold.nii.gz"
t2_out = OUTPUT_DIR / "t2star_map.nii.gz"
nib.save(nib.Nifti1Image(combined, imgs[0].affine, imgs[0].header), str(combined_out))
nib.save(nib.Nifti1Image(t2star, imgs[0].affine, imgs[0].header), str(t2_out))

meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "snapshot_tag": picked["snapshot_tag"],
    "subject_id": picked["subject_id"],
    "session_id": picked["session_id"],
    "run_key": picked["run_key"],
    "echo_count": int(len(local_paths)),
    "echo_indices": [int(v) for v in echo_indices],
    "echo_files": picked["rels"],
    "shape": [int(v) for v in shape],
    "t2star_mean": float(np.mean(t2star)),
    "t2star_max": float(np.max(t2star)),
    "openneuro_queries": int(picked["query_count"]),
    "records_count": 2,
    "bytes_total": int(combined_out.stat().st_size + t2_out.stat().st_size),
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {combined_out} and {t2_out}")
