import json
import os
from pathlib import Path

import mne

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["auditory-lh.stc", "auditory-rh.stc", "source_plot.png"]
OUTPUT_SCHEMA = {
    "auditory-lh.stc": {"type": "file"},
    "auditory-rh.stc": {"type": "file"},
    "source_plot.png": {"type": "png", "min_size_px": [300, 300]},
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
    assert meta.get("task_id") == "ELEC-005"
    assert meta.get("dataset_source") == "Provided"
    assert meta.get("dataset_id") == "mne_sample_dataset"
    assert str(meta.get("status", "")).strip().lower() in {"ok", "failed_precondition"}
    assert str(meta.get("reason", "")).strip()


def test_outputs_parse_and_semantics():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()

    w, h = png_size(OUTPUT_DIR / "source_plot.png")
    assert w >= 300 and h >= 300

    if status == "ok":
        stc = mne.read_source_estimate(str(OUTPUT_DIR / "auditory"), subject=None)
        assert stc.data.shape[0] > 100
        assert stc.data.shape[1] > 50
        assert int(meta.get("n_vertices_lh", 0)) > 0
        assert int(meta.get("n_vertices_rh", 0)) > 0
        assert int(meta.get("n_times", 0)) > 50
    else:
        assert status == "failed_precondition"
        assert (OUTPUT_DIR / "auditory-lh.stc").stat().st_size > 0
        assert (OUTPUT_DIR / "auditory-rh.stc").stat().st_size > 0
