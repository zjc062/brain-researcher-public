import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np
from dipy.core.gradients import gradient_table
from dipy.reconst.dti import TensorModel, fractional_anisotropy
from scipy.special import sph_harm

TASK_ID = "DIFF-011"
DATASET_SOURCE = "Provided"
DATASET_ID = "custom_dwi_data"

output_dir = Path(os.environ["OUTPUT_DIR"]).resolve()
task_dir = Path(os.environ["TASK_DIR"]).resolve()


def candidate_input_dirs(dataset_id: str) -> list[Path]:
    env_input = os.environ.get("INPUT_DIR", "").strip()
    candidates: list[Path] = []
    if env_input:
        candidates.append(Path(env_input))
        candidates.append(Path(env_input) / dataset_id)

    candidates.extend(
        [
            Path("/task/cache") / dataset_id,
            Path("/task/cache"),
            Path("/task/input") / dataset_id,
            Path("/task/input"),
            Path("/app/input") / dataset_id,
            Path("/app/input"),
            task_dir / "input",
            task_dir / "data",
        ]
    )

    uniq: list[Path] = []
    seen = set()
    for p in candidates:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def resolve_input_root(dataset_id: str):
    checked = candidate_input_dirs(dataset_id)
    existing = [p for p in checked if p.exists() and p.is_dir()]
    if not existing:
        return None, checked, [], 0, 0

    best_root = None
    best_files: list[Path] = []
    for root in existing:
        files = [p for p in root.rglob("*") if p.is_file()]
        if len(files) > len(best_files):
            best_root = root
            best_files = files

    if best_root is None:
        return None, checked, [], 0, 0

    file_count = len(best_files)
    byte_count = int(sum(p.stat().st_size for p in best_files))
    return best_root, checked, best_files, file_count, byte_count


def find_dwi(files: list[Path]) -> Path | None:
    candidates = [p for p in files if p.name.endswith("_dwi.nii.gz")]
    if not candidates:
        candidates = [
            p for p in files if "dwi" in p.name.lower() and p.name.endswith((".nii", ".nii.gz"))
        ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: (len(p.parts), p.name))
    return candidates[0]


def sidecar_for(dwi_path: Path, files: list[Path], ext: str) -> Path | None:
    base = dwi_path.name
    if base.endswith(".nii.gz"):
        stem = base[:-7]
    elif base.endswith(".nii"):
        stem = base[:-4]
    else:
        stem = dwi_path.stem

    direct = dwi_path.with_name(f"{stem}.{ext}")
    if direct.exists():
        return direct

    candidates = [p for p in files if p.name.lower().endswith(f".{ext}")]
    if not candidates:
        return None
    candidates.sort(key=lambda p: (len(p.parts), p.name))
    return candidates[0]


def write_mif(path: Path, coeffs: np.ndarray):
    coeffs = np.asarray(coeffs, dtype="<f4", order="C")
    x, y, z, c = coeffs.shape
    header = (
        "mrtrix image\n"
        f"dim: {x},{y},{z},{c}\n"
        "datatype: Float32LE\n"
        "layout: +0,+1,+2,+3\n"
        "pseudo_fod_model: dti_sh_l2\n"
        "END\n"
    )
    with path.open("wb") as handle:
        handle.write(header.encode("utf-8"))
        handle.write(coeffs.tobytes(order="C"))


def save_nifti(path: Path, arr: np.ndarray, affine: np.ndarray):
    img = nib.Nifti1Image(np.asarray(arr, dtype=np.float32), affine)
    img.header.set_data_dtype(np.float32)
    nib.save(img, path)


def write_run_metadata(
    *,
    status: str,
    reason: str,
    data_root: Path | None,
    checked_paths: list[Path],
    records_count: int,
    bytes_total: int,
    extras: dict | None = None,
):
    payload = {
        "task_id": TASK_ID,
        "dataset_source": DATASET_SOURCE,
        "dataset_id": DATASET_ID,
        "status": status,
        "reason": reason,
        "data_root": str(data_root) if data_root else "",
        "checked_paths": [str(p) for p in checked_paths],
        "records_count": int(records_count),
        "bytes_total": int(bytes_total),
    }
    if extras:
        payload.update(extras)
    (output_dir / "run_metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_failfast(
    reason: str,
    data_root: Path | None,
    checked_paths: list[Path],
    records_count: int,
    bytes_total: int,
):
    peaks = np.zeros((8, 8, 8, 3), dtype=np.float32)
    save_nifti(output_dir / "fod_peaks.nii.gz", peaks, np.eye(4))
    write_mif(output_dir / "fod.mif", np.zeros((8, 8, 8, 6), dtype=np.float32))

    write_run_metadata(
        status="failed_precondition",
        reason=reason,
        data_root=data_root,
        checked_paths=checked_paths,
        records_count=records_count,
        bytes_total=bytes_total,
        extras={
            "input_dwi_path": "",
            "input_bval_path": "",
            "input_bvec_path": "",
            "n_volumes": 1,
            "fod_dim": [8, 8, 8, 6],
            "mean_peak_norm": 0.0,
        },
    )


root, checked_paths, files, file_count, byte_count = resolve_input_root(DATASET_ID)
if root is None or file_count == 0:
    write_failfast("missing_input_dir_or_empty", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)


dwi_path = find_dwi(files)
if dwi_path is None:
    write_failfast("missing_dwi_nifti", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)

bval_path = sidecar_for(dwi_path, files, "bval")
bvec_path = sidecar_for(dwi_path, files, "bvec")
if bval_path is None or bvec_path is None:
    write_failfast("missing_bval_or_bvec", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)


try:
    dwi_img = nib.load(str(dwi_path))
    data = np.asarray(dwi_img.dataobj, dtype=np.float32)
    if data.ndim == 3:
        data = data[..., np.newaxis]
    if data.ndim != 4:
        write_failfast("invalid_dwi_shape", root, checked_paths, file_count, byte_count)
        raise SystemExit(0)

    bvals = np.atleast_1d(np.loadtxt(str(bval_path), dtype=float)).reshape(-1)
    bvecs = np.loadtxt(str(bvec_path), dtype=float)
    bvecs = np.asarray(bvecs, dtype=float)
    if bvecs.ndim == 1:
        bvecs = bvecs.reshape(1, -1)
    if bvecs.shape[0] == 3 and bvecs.shape[1] != 3:
        bvecs = bvecs.T

    n = min(int(data.shape[3]), int(bvals.shape[0]), int(bvecs.shape[0]))
    if n < 7:
        write_failfast("insufficient_diffusion_volumes", root, checked_paths, file_count, byte_count)
        raise SystemExit(0)

    data = data[..., :n]
    bvals = bvals[:n]
    bvecs = bvecs[:n]

    gtab = gradient_table(bvals=bvals, bvecs=bvecs, b0_threshold=50)
    b0_idx = np.where(bvals < 80.0)[0]
    if b0_idx.size == 0:
        b0_idx = np.array([0], dtype=int)
    b0 = np.mean(data[..., b0_idx], axis=3)
    mask = b0 > np.percentile(b0, 55.0)
    if int(mask.sum()) < 10:
        mask = b0 > float(b0.mean())
    if int(mask.sum()) < 5:
        mask = np.ones(b0.shape, dtype=bool)

    fit = TensorModel(gtab).fit(data, mask=mask)
    evals = np.clip(fit.evals, a_min=0.0, a_max=None)
    fa = np.nan_to_num(fractional_anisotropy(evals), nan=0.0, posinf=0.0, neginf=0.0)

    evecs = np.asarray(fit.evecs)
    principal = np.nan_to_num(evecs[..., :, 0], nan=0.0, posinf=0.0, neginf=0.0)

    norm = np.linalg.norm(principal, axis=-1, keepdims=True)
    norm = np.where(norm < 1e-8, 1.0, norm)
    unit = principal / norm

    theta = np.arccos(np.clip(unit[..., 2], -1.0, 1.0))
    phi = np.mod(np.arctan2(unit[..., 1], unit[..., 0]), 2.0 * np.pi)

    harmonics = [
        (0, 0),
        (-2, 2),
        (-1, 2),
        (0, 2),
        (1, 2),
        (2, 2),
    ]

    coeffs = np.zeros(fa.shape + (len(harmonics),), dtype=np.float32)
    amp = fa * mask.astype(np.float32)
    for k, (m, l) in enumerate(harmonics):
        ylm = sph_harm(m, l, phi, theta)
        coeffs[..., k] = np.real(ylm).astype(np.float32) * amp

    peaks = unit * amp[..., np.newaxis]
    peaks = np.nan_to_num(peaks, nan=0.0, posinf=0.0, neginf=0.0)

    save_nifti(output_dir / "fod_peaks.nii.gz", peaks, dwi_img.affine)
    write_mif(output_dir / "fod.mif", coeffs)

    peak_norm = np.linalg.norm(peaks, axis=-1)
    mean_peak_norm = float(np.mean(peak_norm[mask])) if np.any(mask) else float(np.mean(peak_norm))

    write_run_metadata(
        status="ok",
        reason="computed",
        data_root=root,
        checked_paths=checked_paths,
        records_count=file_count,
        bytes_total=byte_count,
        extras={
            "input_dwi_path": str(dwi_path),
            "input_bval_path": str(bval_path),
            "input_bvec_path": str(bvec_path),
            "n_volumes": int(n),
            "fod_dim": [int(v) for v in coeffs.shape],
            "mean_peak_norm": mean_peak_norm,
            "mask_voxels": int(mask.sum()),
        },
    )
except Exception as exc:
    write_failfast(f"compute_error: {exc.__class__.__name__}", root, checked_paths, file_count, byte_count)
