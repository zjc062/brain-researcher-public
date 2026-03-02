import json
import os
from pathlib import Path

import mne
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["clean_raw.fif", "preprocessing_report.html"]
OUTPUT_SCHEMA = {
    "clean_raw.fif": {"type": "file"},
    "preprocessing_report.html": {"type": "html"},
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

    assert meta.get("task_id") == "ELEC-001"
    assert meta.get("dataset_source") == "Provided"
    assert meta.get("dataset_id") == "mne_sample_dataset"

    status = str(meta.get("status", "")).strip().lower()
    reason = str(meta.get("reason", "")).strip()
    assert status in {"ok", "failed_precondition"}
    assert reason
    assert int(meta.get("records_count", 0)) >= 0
    assert int(meta.get("bytes_total", 0)) >= 0


def test_outputs_parse_and_semantics():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()

    html_text = (OUTPUT_DIR / "preprocessing_report.html").read_text(encoding="utf-8", errors="ignore").lower()
    assert "<html" in html_text

    raw = mne.io.read_raw_fif(OUTPUT_DIR / "clean_raw.fif", preload=False, verbose="ERROR")
    assert len(raw.ch_names) >= 2
    assert raw.n_times > 100

    if status == "ok":
        assert len(raw.ch_names) >= 100
        assert raw.n_times > 1000
        assert float(raw.info["sfreq"]) >= 100.0
        data = raw.get_data(start=0, stop=min(raw.n_times, 200))
        assert np.all(np.isfinite(data))
        assert "maxwell" in html_text
        assert "filter" in html_text
    else:
        assert status == "failed_precondition"
