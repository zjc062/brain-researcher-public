import json
import os
import re
from pathlib import Path

import nibabel as nib
import numpy as np

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["fod.mif", "fod_peaks.nii.gz"]
OUTPUT_SCHEMA = {
    "fod.mif": {"type": "file"},
    "fod_peaks.nii.gz": {"type": "nifti", "no_nan": True},
}
METRIC_VALIDATION = {}


DIM_RE = re.compile(r"^dim:\s*([0-9]+),([0-9]+),([0-9]+),([0-9]+)\s*$")


def _read_mif(path: Path):
    blob = path.read_bytes()
    marker = b"END\n"
    idx = blob.find(marker)
    assert idx > 0, "fod.mif missing END marker"
    header_bytes = blob[: idx + len(marker)]
    payload = blob[idx + len(marker) :]
    header = header_bytes.decode("utf-8", errors="ignore")

    dims = None
    for line in header.splitlines():
        m = DIM_RE.match(line.strip())
        if m:
            dims = tuple(int(x) for x in m.groups())
            break

    assert dims is not None, "fod.mif header missing dim"
    return header, dims, payload


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        p = OUTPUT_DIR / name
        assert p.exists(), f"Missing required output: {p}"
        assert p.is_file(), f"Required output is not a file: {p}"



def test_run_metadata_contract():
    meta_path = OUTPUT_DIR / "run_metadata.json"
    assert meta_path.exists(), "run_metadata.json is required"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    assert meta.get("task_id") == "DIFF-011"
    assert meta.get("dataset_source") == "Provided"
    assert meta.get("dataset_id") == "custom_dwi_data"

    status = str(meta.get("status", "")).strip().lower()
    reason = str(meta.get("reason", "")).strip()
    assert status in {"ok", "failed_precondition"}
    assert reason
    assert int(meta.get("records_count", 0)) >= 0
    assert int(meta.get("bytes_total", 0)) >= 0



def test_fod_file_and_peaks_semantics():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    status = str(meta.get("status", "")).strip().lower()

    header, dims, payload = _read_mif(OUTPUT_DIR / "fod.mif")
    assert "mrtrix image" in header.lower()
    assert "datatype" in header.lower()
    assert "pseudo_fod_model" in header.lower()

    expected_payload = int(np.prod(dims) * 4)
    assert len(payload) >= expected_payload, "fod.mif payload appears truncated"

    peaks = np.asarray(nib.load(str(OUTPUT_DIR / "fod_peaks.nii.gz")).dataobj)
    assert peaks.ndim == 4 and peaks.shape[-1] == 3
    assert np.all(np.isfinite(peaks)), "fod_peaks has non-finite values"

    assert tuple(dims[:3]) == tuple(int(v) for v in peaks.shape[:3])
    assert int(dims[3]) >= 6

    if status == "ok":
        assert int(meta.get("n_volumes", 0)) >= 7

        input_path = Path(str(meta.get("input_dwi_path", "")))
        assert input_path.exists(), "input_dwi_path in run_metadata must exist"

        peak_norm = np.linalg.norm(peaks, axis=-1)
        assert float(np.percentile(peak_norm, 99)) > 0.01

        mean_peak_norm = float(meta.get("mean_peak_norm", -1.0))
        assert mean_peak_norm >= 0.0
        assert abs(mean_peak_norm - float(np.mean(peak_norm[peak_norm > 0]))) < 0.2

        fod_dim = meta.get("fod_dim")
        assert fod_dim == [int(dims[0]), int(dims[1]), int(dims[2]), int(dims[3])]
    else:
        assert status == "failed_precondition"

