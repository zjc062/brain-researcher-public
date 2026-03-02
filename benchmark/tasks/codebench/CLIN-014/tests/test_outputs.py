import json
import os
import pickle
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["responder_model.pkl", "predictive_map.nii.gz"]
OUTPUT_SCHEMA = {
    "responder_model.pkl": {"type": "pickle"},
    "predictive_map.nii.gz": {"type": "nifti", "no_nan": True},
}
METRIC_VALIDATION = {}


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        path = OUTPUT_DIR / name
        assert path.exists(), f"Missing required output: {path}"
        assert path.is_file(), f"Required output is not a file: {path}"


def test_pickle_model_schema():
    with (OUTPUT_DIR / "responder_model.pkl").open("rb") as handle:
        model = pickle.load(handle)

    assert isinstance(model, dict), "responder_model.pkl must contain a dict"
    assert model.get("task_id") == "CLIN-014"
    assert model.get("dataset_source") == "Provided"
    assert model.get("dataset_id") == "simulated_treatment_dataset"

    status = str(model.get("status", "")).strip().lower()
    assert status in {"ok", "failed_precondition"}
    assert str(model.get("reason", "")).strip(), "model reason must be non-empty"

    if status == "ok":
        assert isinstance(model.get("weights"), list) and len(model["weights"]) > 0
        assert isinstance(model.get("feature_names"), list) and len(model["feature_names"]) == len(model["weights"])
        assert 0.0 <= float(model.get("train_accuracy")) <= 1.0
        assert 0.0 <= float(model.get("train_auc")) <= 1.0


def test_predictive_map_nifti_valid():
    img = nib.load(str(OUTPUT_DIR / "predictive_map.nii.gz"))
    arr = np.asarray(img.get_fdata(), dtype=float)

    assert arr.ndim == 3
    assert np.all(np.isfinite(arr)), "predictive_map contains non-finite values"
    assert arr.shape[0] > 0 and arr.shape[1] > 0 and arr.shape[2] > 0


def test_cross_file_consistency_with_run_metadata():
    meta_path = OUTPUT_DIR / "run_metadata.json"
    assert meta_path.exists(), "run_metadata.json is required"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    with (OUTPUT_DIR / "responder_model.pkl").open("rb") as handle:
        model = pickle.load(handle)

    assert meta.get("task_id") == "CLIN-014"
    assert meta.get("dataset_source") == "Provided"
    assert meta.get("dataset_id") == "simulated_treatment_dataset"

    run_status = str(meta.get("status", "")).strip().lower()
    model_status = str(model.get("status", "")).strip().lower()
    run_reason = str(meta.get("reason", "")).strip()
    model_reason = str(model.get("reason", "")).strip()
    assert run_status == model_status
    assert run_reason
    assert model_reason == run_reason

    if run_status == "ok":
        assert int(meta.get("n_subjects_used")) >= 6
        assert int(meta.get("n_subjects_responder")) >= 2
        assert int(meta.get("n_subjects_non_responder")) >= 2
        assert 0.0 <= float(meta.get("train_accuracy")) <= 1.0
        assert 0.0 <= float(meta.get("train_auc")) <= 1.0

        img = nib.load(str(OUTPUT_DIR / "predictive_map.nii.gz"))
        arr = np.asarray(img.get_fdata(), dtype=float)
        assert np.std(arr) > 0.0, "predictive_map should not be constant in ok mode"
        assert abs(float(np.mean(arr)) - float(meta.get("predictive_map_mean"))) <= 1e-6
    else:
        assert run_status == "failed_precondition"
        assert int(meta.get("n_subjects_used")) == 0
        assert str(meta.get("reason", "")).strip()
