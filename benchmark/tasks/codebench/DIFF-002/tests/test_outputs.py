import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["dti_FA.nii.gz", "dti_MD.nii.gz", "dti_tensors.nii.gz"]
OUTPUT_SCHEMA = {
    "dti_FA.nii.gz": {"type": "nifti", "no_nan": True},
    "dti_MD.nii.gz": {"type": "nifti", "no_nan": True},
    "dti_tensors.nii.gz": {"type": "nifti", "no_nan": True},
}
METRIC_VALIDATION = {}


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Required output is not a file: {p}"



def test_run_metadata_contract():
    meta_path = OUTPUT_DIR / "run_metadata.json"
    assert meta_path.exists(), "run_metadata.json is required"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta.get("task_id") == "DIFF-002"
    assert meta.get("dataset_source") == "Provided"
    assert meta.get("dataset_id") == "custom_dwi_data"

    status = str(meta.get("status", "")).strip().lower()
    reason = str(meta.get("reason", "")).strip()
    assert status in {"ok", "failed_precondition"}
    assert reason
    assert int(meta.get("records_count", 0)) >= 0
    assert int(meta.get("bytes_total", 0)) >= 0



def test_tensor_outputs_semantics_and_alignment():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()

    fa = np.asarray(nib.load(str(OUTPUT_DIR / "dti_FA.nii.gz")).dataobj)
    md = np.asarray(nib.load(str(OUTPUT_DIR / "dti_MD.nii.gz")).dataobj)
    tensor = np.asarray(nib.load(str(OUTPUT_DIR / "dti_tensors.nii.gz")).dataobj)

    assert fa.ndim == 3
    assert md.ndim == 3
    assert tensor.ndim == 4 and tensor.shape[-1] == 6
    assert fa.shape == md.shape == tensor.shape[:3]

    assert np.all(np.isfinite(fa)), "FA map has non-finite values"
    assert np.all(np.isfinite(md)), "MD map has non-finite values"
    assert np.all(np.isfinite(tensor)), "Tensor map has non-finite values"

    if status == "ok":
        assert int(meta.get("n_volumes", 0)) >= 7
        assert int(meta.get("mask_voxels", 0)) > 0

        input_path = Path(str(meta.get("input_dwi_path", "")))
        assert input_path.exists(), "input_dwi_path in run_metadata must exist"

        fa_nonzero = fa[fa > 0]
        md_nonzero = md[md > 0]
        assert fa_nonzero.size > 0, "FA appears empty in ok mode"
        assert md_nonzero.size > 0, "MD appears empty in ok mode"

        assert float(np.percentile(fa_nonzero, 99)) <= 1.5
        assert float(np.percentile(md_nonzero, 99)) <= 0.01

        mean_fa = float(meta.get("mean_fa", -1.0))
        mean_md = float(meta.get("mean_md", -1.0))
        assert 0.0 <= mean_fa <= 1.2
        assert 0.0 <= mean_md <= 0.01
        assert abs(mean_fa - float(np.mean(fa_nonzero))) < 0.2
        assert abs(mean_md - float(np.mean(md_nonzero))) < 0.002
    else:
        assert status == "failed_precondition"

