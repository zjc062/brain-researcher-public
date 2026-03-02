import json
import os
from pathlib import Path

import mne

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["tfr_average.h5", "time_frequency_plot.png"]
OUTPUT_SCHEMA = {
    "tfr_average.h5": {"type": "file"},
    "time_frequency_plot.png": {"type": "png", "min_size_px": [300, 300]},
}
METRIC_VALIDATION = {}

def png_size(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    assert header[:8] == b"\x89PNG\r\n\x1a\n", f"Invalid PNG signature: {path}"
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    return width, height


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Required output is not a file: {p}"


def test_run_metadata_contract():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta.get("task_id") == "ELEC-004"
    assert meta.get("dataset_source") == "Provided"
    assert meta.get("dataset_id") == "mne_sample_dataset"
    assert str(meta.get("status", "")).strip().lower() in {"ok", "failed_precondition"}
    assert str(meta.get("reason", "")).strip()


def test_outputs_parse_and_semantics():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()

    tfr = mne.time_frequency.read_tfrs(OUTPUT_DIR / "tfr_average.h5")
    if isinstance(tfr, list):
        tfr = tfr[0]
    assert tfr.data.ndim == 3
    assert tfr.data.shape[0] >= 1
    assert tfr.data.shape[1] >= 3
    assert tfr.data.shape[2] >= 10

    w, h = png_size(OUTPUT_DIR / "time_frequency_plot.png")
    assert w >= 300 and h >= 300

    if status == "ok":
        assert float(tfr.freqs.min()) >= 29.0
        assert float(tfr.freqs.max()) <= 51.0
        assert int(meta.get("n_freqs", 0)) >= 3
        assert int(meta.get("n_times", 0)) >= 10
    else:
        assert status == "failed_precondition"
