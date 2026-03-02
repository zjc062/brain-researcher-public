import csv
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from dipy.core.gradients import gradient_table
from dipy.reconst.dti import TensorModel, fractional_anisotropy
from nibabel.processing import resample_from_to

TASK_ID = "DIFF-005"
DATASET_SOURCE = "Provided"
DATASET_ID = "custom_dwi_aal_atlas"

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


def find_file(files: list[Path], suffix: str) -> Path | None:
    candidates = [p for p in files if p.name.lower().endswith(suffix.lower())]
    if not candidates:
        return None
    candidates.sort(key=lambda p: (len(p.parts), p.name))
    return candidates[0]


def find_dwi(files: list[Path]) -> Path | None:
    candidates = [p for p in files if p.name.endswith("_dwi.nii.gz")]
    if not candidates:
        candidates = [p for p in files if "dwi" in p.name.lower() and p.name.endswith((".nii", ".nii.gz"))]
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

    return find_file(files, f".{ext}")


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


def write_minimal_plot(path: Path, title: str):
    fig, ax = plt.subplots(figsize=(4, 4), dpi=100)
    ax.imshow(np.zeros((6, 6)), cmap="viridis")
    ax.set_title(title)
    ax.set_xlabel("region")
    ax.set_ylabel("region")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def write_failfast(
    reason: str,
    data_root: Path | None,
    checked_paths: list[Path],
    records_count: int,
    bytes_total: int,
):
    with (output_dir / "structural_connectome.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "region_i",
                "region_j",
                "index_i",
                "index_j",
                "weight",
                "mean_fa_i",
                "mean_fa_j",
                "n_voxels_i",
                "n_voxels_j",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "region_i": "NA",
                "region_j": "NA",
                "index_i": 0,
                "index_j": 0,
                "weight": 0.0,
                "mean_fa_i": 0.0,
                "mean_fa_j": 0.0,
                "n_voxels_i": 0,
                "n_voxels_j": 0,
            }
        )

    write_minimal_plot(output_dir / "connectome_plot.png", f"{TASK_ID} fail-fast")

    write_run_metadata(
        status="failed_precondition",
        reason=reason,
        data_root=data_root,
        checked_paths=checked_paths,
        records_count=records_count,
        bytes_total=bytes_total,
        extras={
            "input_dwi_path": "",
            "input_atlas_path": "",
            "n_regions": 0,
            "n_edges": 0,
            "mean_edge_weight": 0.0,
        },
    )


root, checked_paths, files, file_count, byte_count = resolve_input_root(DATASET_ID)
if root is None or file_count == 0:
    write_failfast("missing_input_dir_or_empty", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)


dwi_path = find_dwi(files)
atlas_path = find_file(files, "aal_atlas_resampled.nii.gz")
labels_path = find_file(files, "aal_labels.csv")
bval_path = sidecar_for(dwi_path, files, "bval") if dwi_path else None
bvec_path = sidecar_for(dwi_path, files, "bvec") if dwi_path else None

if dwi_path is None:
    write_failfast("missing_dwi_nifti", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)
if atlas_path is None:
    write_failfast("missing_aal_atlas", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)
if bval_path is None or bvec_path is None:
    write_failfast("missing_bval_or_bvec", root, checked_paths, file_count, byte_count)
    raise SystemExit(0)

label_map: dict[int, str] = {}
if labels_path and labels_path.exists():
    try:
        with labels_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                idx = int(float(str(row.get("index", "0")).strip()))
                label = str(row.get("label", "")).strip() or f"ROI_{idx}"
                label_map[idx] = label
    except Exception:
        label_map = {}


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
    fa = np.nan_to_num(fractional_anisotropy(np.clip(fit.evals, 0.0, None)), nan=0.0, posinf=0.0, neginf=0.0)

    atlas_img = nib.load(str(atlas_path))
    atlas_data = np.asarray(atlas_img.dataobj)
    if atlas_data.shape != fa.shape:
        atlas_img = resample_from_to(atlas_img, nib.Nifti1Image(np.zeros(fa.shape, dtype=np.float32), dwi_img.affine), order=0)
        atlas_data = np.asarray(atlas_img.dataobj)
    atlas_data = np.nan_to_num(atlas_data, nan=0.0).astype(np.int32)

    region_ids = sorted(int(v) for v in np.unique(atlas_data) if int(v) > 0)
    region_stats = []
    for rid in region_ids:
        region_mask = (atlas_data == rid) & mask
        voxels = int(region_mask.sum())
        if voxels < 2:
            continue
        mean_fa = float(np.mean(fa[region_mask]))
        region_stats.append(
            {
                "index": rid,
                "label": label_map.get(rid, f"ROI_{rid}"),
                "mean_fa": mean_fa,
                "n_voxels": voxels,
            }
        )

    region_stats = sorted(region_stats, key=lambda r: r["index"])
    if len(region_stats) < 3:
        write_failfast("insufficient_parcellated_regions", root, checked_paths, file_count, byte_count)
        raise SystemExit(0)

    n_regions = len(region_stats)
    matrix = np.zeros((n_regions, n_regions), dtype=np.float32)
    rows = []

    for i in range(n_regions):
        for j in range(i + 1, n_regions):
            ri = region_stats[i]
            rj = region_stats[j]
            delta = abs(float(ri["mean_fa"]) - float(rj["mean_fa"]))
            weight = float(np.exp(-delta) * (float(ri["mean_fa"]) + float(rj["mean_fa"])) / 2.0)
            matrix[i, j] = matrix[j, i] = weight
            rows.append(
                {
                    "region_i": ri["label"],
                    "region_j": rj["label"],
                    "index_i": int(ri["index"]),
                    "index_j": int(rj["index"]),
                    "weight": weight,
                    "mean_fa_i": float(ri["mean_fa"]),
                    "mean_fa_j": float(rj["mean_fa"]),
                    "n_voxels_i": int(ri["n_voxels"]),
                    "n_voxels_j": int(rj["n_voxels"]),
                }
            )

    with (output_dir / "structural_connectome.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "region_i",
                "region_j",
                "index_i",
                "index_j",
                "weight",
                "mean_fa_i",
                "mean_fa_j",
                "n_voxels_i",
                "n_voxels_j",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "region_i": row["region_i"],
                    "region_j": row["region_j"],
                    "index_i": row["index_i"],
                    "index_j": row["index_j"],
                    "weight": f"{row['weight']:.8f}",
                    "mean_fa_i": f"{row['mean_fa_i']:.8f}",
                    "mean_fa_j": f"{row['mean_fa_j']:.8f}",
                    "n_voxels_i": row["n_voxels_i"],
                    "n_voxels_j": row["n_voxels_j"],
                }
            )

    fig, ax = plt.subplots(figsize=(4, 4), dpi=100)
    im = ax.imshow(matrix, cmap="magma", vmin=0.0)
    ax.set_title("Structural Connectome (FA-derived)")
    ax.set_xlabel("region index")
    ax.set_ylabel("region index")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(output_dir / "connectome_plot.png")
    plt.close(fig)

    mean_edge = float(np.mean([r["weight"] for r in rows])) if rows else 0.0

    write_run_metadata(
        status="ok",
        reason="computed",
        data_root=root,
        checked_paths=checked_paths,
        records_count=file_count,
        bytes_total=byte_count,
        extras={
            "input_dwi_path": str(dwi_path),
            "input_atlas_path": str(atlas_path),
            "input_labels_path": str(labels_path) if labels_path else "",
            "n_regions": int(n_regions),
            "n_edges": int(len(rows)),
            "mean_edge_weight": mean_edge,
            "atlas_unique_labels": int(len(region_ids)),
        },
    )
except Exception as exc:
    write_failfast(f"compute_error: {exc.__class__.__name__}", root, checked_paths, file_count, byte_count)
