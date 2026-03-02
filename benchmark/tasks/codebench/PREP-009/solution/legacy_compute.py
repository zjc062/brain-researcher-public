import json
import os
import re
import urllib.request
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np

TASK_ID = "PREP-009"
DATASET_ID = "ds000030"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"
LOW_HZ = 0.01
HIGH_HZ = 0.10

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

            rest_bolds = [
                f for f in bolds if re.search(r"(?:^|[_-])rest(?:[_-]|\.|$)", str(f.get("filename", "")).lower())
            ]
            chosen = rest_bolds[0] if rest_bolds else bolds[0]
            ses_name = ses["filename"] or "nosession"
            rel_prefix = sub["filename"] + (f"/{ses_name}" if ses_name != "nosession" else "")
            rel = f"{rel_prefix}/func/{chosen['filename']}"
            return {
                "snapshot_tag": snapshot_tag,
                "subject_id": sub["filename"],
                "session_id": ses_name,
                "bold": chosen,
                "bold_relpath": rel,
                "query_count": query_count,
            }

    raise RuntimeError(f"No BOLD file found in {DATASET_ID}")


picked = find_first_bold_file()
bold_path = CACHE_DIR / picked["bold_relpath"]
if not bold_path.exists():
    download(picked["bold"]["urls"][0], bold_path)

img = nib.load(str(bold_path))
data = np.asarray(img.get_fdata(), dtype=np.float32)
if data.ndim != 4 or data.shape[3] < 20:
    raise RuntimeError(f"Unexpected BOLD shape: {data.shape}")

nx, ny, nz, nt = data.shape
tr = float(img.header.get_zooms()[3]) if len(img.header.get_zooms()) >= 4 else 1.0
if not np.isfinite(tr) or tr <= 0:
    tr = 1.0

Y = data.reshape(-1, nt).T.astype(np.float32)  # (T, V)
freqs = np.fft.rfftfreq(nt, d=tr)
band_mask = (freqs >= LOW_HZ) & (freqs <= HIGH_HZ)

Yf = np.empty_like(Y, dtype=np.float32)
chunk = 20000
for start in range(0, Y.shape[1], chunk):
    end = min(start + chunk, Y.shape[1])
    block = Y[:, start:end]
    F = np.fft.rfft(block, axis=0)
    F[~band_mask, :] = 0
    Yf[:, start:end] = np.fft.irfft(F, n=nt, axis=0).astype(np.float32)

filtered = Yf.T.reshape(nx, ny, nz, nt)

# Diagnostics: global power spectra before/after.
g_pre = np.mean(Y, axis=1)
g_post = np.mean(Yf, axis=1)
P_pre = np.abs(np.fft.rfft(g_pre)) ** 2
P_post = np.abs(np.fft.rfft(g_post)) ** 2

hf_mask = freqs > HIGH_HZ
hf_pre = float(np.sum(P_pre[hf_mask]) / (np.sum(P_pre[1:]) + 1e-12))
hf_post = float(np.sum(P_post[hf_mask]) / (np.sum(P_post[1:]) + 1e-12))

nifti_out = OUTPUT_DIR / "filtered_bold.nii.gz"
png_out = OUTPUT_DIR / "power_spectrum.png"
nib.save(nib.Nifti1Image(filtered, img.affine, img.header), str(nifti_out))

plt.figure(figsize=(6, 4))
plt.plot(freqs[1:], P_pre[1:], label="before", alpha=0.8)
plt.plot(freqs[1:], P_post[1:], label="after", alpha=0.8)
plt.axvline(LOW_HZ, color="k", linestyle="--", linewidth=1)
plt.axvline(HIGH_HZ, color="k", linestyle="--", linewidth=1)
plt.xlabel("Frequency (Hz)")
plt.ylabel("Power")
plt.title("Global Signal Power Spectrum")
plt.legend()
plt.tight_layout()
plt.savefig(png_out, dpi=120)
plt.close()

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
    "tr": float(tr),
    "low_hz": float(LOW_HZ),
    "high_hz": float(HIGH_HZ),
    "pre_highfreq_ratio": hf_pre,
    "post_highfreq_ratio": hf_post,
    "openneuro_queries": int(picked["query_count"]),
    "records_count": 2,
    "bytes_total": int(nifti_out.stat().st_size + png_out.stat().st_size),
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {nifti_out} and {png_out}")
