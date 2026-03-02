import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn import datasets, image
from scipy.ndimage import gaussian_filter

TASK_ID = "REG-010"
DATASET_ID = "fetch_miyawaki2008"
OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
CACHE_DIR = Path(os.environ["CACHE_DIR"])

if os.environ.get("ML_FORCE_FAIL", "0") == "1" or os.environ.get("REG_FORCE_FAIL", "0") == "1":
    raise RuntimeError("forced_failure")

miy = datasets.fetch_miyawaki2008(data_dir=str(CACHE_DIR), verbose=0)
native_bg = nib.load(str(miy.background))
mni_template = datasets.load_mni152_template(resolution=2)

native_results_img = image.resample_to_img(mni_template, native_bg, interpolation="continuous")
native_results = np.asarray(native_results_img.get_fdata(), dtype=np.float32)

shape = native_bg.shape[:3]
grid = np.indices(shape, dtype=np.float32)
vox = np.stack([grid[0], grid[1], grid[2]], axis=-1).reshape(-1, 3)
hom = np.concatenate([vox, np.ones((vox.shape[0], 1), dtype=np.float32)], axis=1)
world = (native_bg.affine @ hom.T).T
mni_vox = (np.linalg.inv(mni_template.affine) @ world.T).T[:, :3]
disp = mni_vox - vox
warp_mag = np.linalg.norm(disp, axis=1).reshape(shape).astype(np.float32)
warp_mag = gaussian_filter(warp_mag, sigma=1.0).astype(np.float32)

native_out = OUTPUT_DIR / "native_space_results.nii.gz"
warp_out = OUTPUT_DIR / "inverse_warp.nii.gz"
nib.save(nib.Nifti1Image(native_results, native_bg.affine, native_bg.header), str(native_out))
nib.save(nib.Nifti1Image(warp_mag, native_bg.affine, native_bg.header), str(warp_out))

meta = {
    "task_id": TASK_ID,
    "dataset_source": "Nilearn",
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "native_background": str(miy.background),
    "native_shape": [int(v) for v in native_bg.shape[:3]],
    "mni_shape": [int(v) for v in mni_template.shape[:3]],
    "native_results_shape": [int(v) for v in native_results.shape],
    "inverse_warp_shape": [int(v) for v in warp_mag.shape],
    "native_results_mean": float(np.mean(native_results)),
    "warp_mean": float(np.mean(warp_mag)),
    "warp_max": float(np.max(warp_mag)),
    "records_count": 2,
    "bytes_total": int(native_out.stat().st_size + warp_out.stat().st_size),
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {native_out} and {warp_out}")
