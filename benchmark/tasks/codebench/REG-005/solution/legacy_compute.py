import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn import datasets, image

TASK_ID = "REG-005"
DATASET_ID = "fetch_spm_multimodal_fmri"
OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
CACHE_DIR = Path(os.environ["CACHE_DIR"])

if os.environ.get("ML_FORCE_FAIL", "0") == "1" or os.environ.get("REG_FORCE_FAIL", "0") == "1":
    raise RuntimeError("forced_failure")

spm = datasets.fetch_spm_multimodal_fmri(subject_id="sub001", data_dir=str(CACHE_DIR), verbose=0)
anat_path = Path(spm.anat)
func_paths = [Path(p) for p in list(spm.func1)]
if not anat_path.exists() or len(func_paths) < 5:
    raise RuntimeError("SPM multimodal dataset missing required anat/func files")

anat_img = nib.load(str(anat_path))
n_use = min(20, len(func_paths))
func_imgs = [nib.load(str(p)) for p in func_paths[:n_use]]
func_stack = np.stack([np.asarray(img.get_fdata(), dtype=np.float32) for img in func_imgs], axis=0)
t2_proxy_data = np.mean(func_stack, axis=0).astype(np.float32)
t2_proxy_img = nib.Nifti1Image(t2_proxy_data, func_imgs[0].affine, func_imgs[0].header)

coreg_img = image.resample_to_img(anat_img, t2_proxy_img, interpolation="continuous")
coreg_data = np.asarray(coreg_img.get_fdata(), dtype=np.float32)

matrix = np.linalg.inv(t2_proxy_img.affine) @ anat_img.affine

mat_out = OUTPUT_DIR / "t1_to_t2_matrix.mat"
coreg_out = OUTPUT_DIR / "coregistered_t1.nii.gz"
np.savetxt(mat_out, matrix, fmt="%.10f")
nib.save(nib.Nifti1Image(coreg_data, t2_proxy_img.affine, t2_proxy_img.header), str(coreg_out))

meta = {
    "task_id": TASK_ID,
    "dataset_source": "Nilearn",
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "subject_id": "sub001",
    "anat_path": str(anat_path),
    "func_reference_path": str(func_paths[0]),
    "n_func_used": int(n_use),
    "anat_shape": [int(v) for v in anat_img.shape[:3]],
    "t2_proxy_shape": [int(v) for v in t2_proxy_data.shape],
    "coregistered_shape": [int(v) for v in coreg_data.shape],
    "matrix_det": float(np.linalg.det(matrix)),
    "matrix_trace": float(np.trace(matrix)),
    "records_count": 2,
    "bytes_total": int(mat_out.stat().st_size + coreg_out.stat().st_size),
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

print(f"Wrote {mat_out} and {coreg_out}")
