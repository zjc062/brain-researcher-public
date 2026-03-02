import json
import os
from pathlib import Path

import mne

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["auditory_evoked.fif", "visual_evoked.fif", "evoked_plot.png"]
OUTPUT_SCHEMA = {
    "auditory_evoked.fif": {"type": "file"},
    "visual_evoked.fif": {"type": "file"},
    "evoked_plot.png": {"type": "png", "min_size_px": [300, 300]},
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
    assert meta.get("task_id") == "ELEC-003"
    assert meta.get("dataset_source") == "Provided"
    assert meta.get("dataset_id") == "mne_sample_dataset"
    assert str(meta.get("status", "")).strip().lower() in {"ok", "failed_precondition"}
    assert str(meta.get("reason", "")).strip()


def test_outputs_parse_and_semantics():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()

    aud = mne.read_evokeds(OUTPUT_DIR / "auditory_evoked.fif", condition=0, verbose="ERROR")
    vis = mne.read_evokeds(OUTPUT_DIR / "visual_evoked.fif", condition=0, verbose="ERROR")

    assert aud.data.shape[0] == vis.data.shape[0]
    assert aud.data.shape[1] == vis.data.shape[1]
    assert aud.nave >= 1 and vis.nave >= 1

    w, h = png_size(OUTPUT_DIR / "evoked_plot.png")
    assert w >= 300 and h >= 300

    if status == "ok":
        assert aud.data.shape[0] >= 50
        assert aud.data.shape[1] >= 100
        assert int(meta.get("n_auditory_epochs", 0)) >= 1
        assert int(meta.get("n_visual_epochs", 0)) >= 1
    else:
        assert status == "failed_precondition"
