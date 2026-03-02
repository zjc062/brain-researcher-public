import json
import os
from pathlib import Path

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["preflight_check.json", "fail_fast_reason.txt"]
OUTPUT_SCHEMA = {
    "preflight_check.json": {
        "type": "json",
        "required_keys": ["status", "required_inputs", "missing_inputs", "checked_paths"],
    },
    "fail_fast_reason.txt": {"type": "text"},
}
METRIC_VALIDATION = {
    "status": {"expected": "failed_precondition"},
    "missing_inputs_count": {"min": 1},
}


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        path = OUTPUT_DIR / name
        assert path.exists(), f"Missing required output: {path}"
        assert path.is_file(), f"Required output is not a file: {path}"


def test_preflight_json_schema_and_fail_fast_semantics():
    preflight = json.loads((OUTPUT_DIR / "preflight_check.json").read_text(encoding="utf-8"))
    for key in OUTPUT_SCHEMA["preflight_check.json"]["required_keys"]:
        assert key in preflight, f"Missing preflight key: {key}"

    assert preflight["status"] == "failed_precondition"
    assert preflight.get("reason") in {"missing_input_root", "missing_required_modalities"}

    required_inputs = preflight["required_inputs"]
    missing_inputs = preflight["missing_inputs"]
    checked_paths = preflight["checked_paths"]

    assert required_inputs == ["anat_t1w", "func_bold", "dwi", "events_tsv"]
    assert isinstance(missing_inputs, list)
    assert len(missing_inputs) >= 1
    assert set(missing_inputs).issubset(set(required_inputs))
    assert isinstance(checked_paths, list) and len(checked_paths) >= 1

    assert int(preflight.get("missing_inputs_count", -1)) == len(missing_inputs)
    assert int(preflight.get("n_scanned_files", -1)) >= 0


def test_fail_fast_reason_text():
    text = (OUTPUT_DIR / "fail_fast_reason.txt").read_text(encoding="utf-8")
    preflight = json.loads((OUTPUT_DIR / "preflight_check.json").read_text(encoding="utf-8"))

    assert "FAILED_PRECONDITION" in text
    assert f"reason={preflight['reason']}" in text
    assert "missing_inputs=" in text


def test_run_metadata_traceability_and_consistency():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    preflight = json.loads((OUTPUT_DIR / "preflight_check.json").read_text(encoding="utf-8"))

    assert meta["task_id"] == "DATA-017"
    assert meta["dataset_source"] == "Provided"
    assert meta["dataset_id"] == "custom_missing_modalities"
    assert meta["status"] == "failed_precondition"
    assert meta["reason"] == preflight["reason"]
    assert int(meta["missing_inputs_count"]) == int(preflight["missing_inputs_count"])
    assert list(meta["missing_inputs"]) == list(preflight["missing_inputs"])
    assert list(meta["required_inputs"]) == list(preflight["required_inputs"])
