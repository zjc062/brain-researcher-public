import csv
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy.ndimage import center_of_mass, shift

TASK_ID = "DIFF-001"
DATASET_SOURCE = "Provided"
DATASET_ID = "custom_dwi_bids"

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


def find_dwi_file(files: list[Path]) -> Path | None:
    candidates = [p for p in files if p.name.endswith("_dwi.nii.gz")]
    if not candidates:
        candidates = [
            p
            for p in files
            if p.suffix.lower() in {".nii", ".gz"} and "dwi" in p.name.lower() and p.name.endswith((".nii", ".nii.gz"))
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
    minimal_volume = np.zeros((8, 8, 8, 1), dtype=np.float32)
    nib.save(nib.Nifti1Image(minimal_volume, np.eye(4)), output_dir / "corrected_dwi.nii.gz")

    with (output_dir / "eddy_movement.txt").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["volume", "bval", "shift_x", "shift_y", "shift_z", "scale"])
        writer.writerow([0, 0.0, 0.0, 0.0, 0.0, 1.0])

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
            "n_volumes": 1,
            "mean_abs_shift_vox": 0.0,
        },
    )


root, checked_paths, files, file_count, byte_count = resolve_input_root(DATASET_ID)
if root is None or file_count == 0:
    write_failfast("missing_input_dir_or_empty", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)


dwi_path = find_dwi_file(files)
if dwi_path is None:
    write_failfast("missing_dwi_nifti", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)

bval_path = sidecar_for(dwi_path, files, "bval")
if bval_path is None:
    write_failfast("missing_bval", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)


try:
    img = nib.load(str(dwi_path))
    data = np.asarray(img.dataobj, dtype=np.float32)
    if data.ndim == 3:
        data = data[..., np.newaxis]
    if data.ndim != 4:
        write_failfast("invalid_dwi_shape", root, checked_paths, file_count, byte_count)
        raise SystemExit(0)

    bvals = np.loadtxt(str(bval_path), dtype=float)
    bvals = np.atleast_1d(bvals).reshape(-1)
    n_vol = int(data.shape[3])

    if bvals.size < n_vol:
        bvals = np.pad(bvals, (0, n_vol - bvals.size), mode="edge")
    elif bvals.size > n_vol:
        bvals = bvals[:n_vol]

    b0_idx = np.where(bvals < 80.0)[0]
    if b0_idx.size == 0:
        b0_idx = np.array([0], dtype=int)

    ref = np.mean(data[..., b0_idx], axis=3)
    mask = ref > np.percentile(ref, 60.0)
    if int(mask.sum()) < 20:
        mask = ref > float(ref.mean())
    if int(mask.sum()) < 5:
        mask = np.ones(ref.shape, dtype=bool)

    ref_weighted = np.clip(ref, a_min=0.0, a_max=None) * mask.astype(np.float32)
    ref_com = np.array(center_of_mass(ref_weighted), dtype=float)

    corrected = np.zeros_like(data, dtype=np.float32)
    motion_rows: list[list[float]] = []

    ref_mean = float(ref[mask].mean()) if np.any(mask) else float(ref.mean())
    if not np.isfinite(ref_mean) or ref_mean <= 1e-6:
        ref_mean = 1.0

    for idx in range(n_vol):
        vol = data[..., idx]
        weighted = np.clip(vol, a_min=0.0, a_max=None) * mask.astype(np.float32)
        vol_com = np.array(center_of_mass(weighted), dtype=float)
        if not np.all(np.isfinite(vol_com)):
            vol_com = ref_com.copy()

        delta = ref_com - vol_com
        moved = shift(vol, shift=tuple(delta.tolist()), order=1, mode="nearest", prefilter=False)

        vol_mean = float(moved[mask].mean()) if np.any(mask) else float(moved.mean())
        if not np.isfinite(vol_mean) or vol_mean <= 1e-6:
            scale = 1.0
        else:
            scale = float(ref_mean / vol_mean)

        corrected[..., idx] = moved * scale
        motion_rows.append([float(idx), float(bvals[idx]), float(delta[0]), float(delta[1]), float(delta[2]), float(scale)])

    hdr = img.header.copy()
    hdr.set_data_dtype(np.float32)
    nib.save(nib.Nifti1Image(corrected, img.affine, hdr), output_dir / "corrected_dwi.nii.gz")

    with (output_dir / "eddy_movement.txt").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["volume", "bval", "shift_x", "shift_y", "shift_z", "scale"])
        for row in motion_rows:
            writer.writerow(
                [
                    int(row[0]),
                    f"{row[1]:.1f}",
                    f"{row[2]:.6f}",
                    f"{row[3]:.6f}",
                    f"{row[4]:.6f}",
                    f"{row[5]:.6f}",
                ]
            )

    mean_abs_shift = float(np.mean([np.linalg.norm(np.asarray(r[2:5], dtype=float)) for r in motion_rows]))

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
            "n_volumes": int(n_vol),
            "mean_abs_shift_vox": mean_abs_shift,
            "reference_b0_count": int(b0_idx.size),
            "mask_voxels": int(mask.sum()),
        },
    )
except Exception as exc:
    write_failfast(f"compute_error: {exc.__class__.__name__}", root, checked_paths, file_count, byte_count)
