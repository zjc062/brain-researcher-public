import csv
import json
import os
import re
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
from scipy import stats

TASK_ID = "CLIN-006"
DATASET_SOURCE = "Provided"
DATASET_ID = "simulated_lesion_symptom_data"

output_dir = Path(os.environ["OUTPUT_DIR"]).resolve()
task_dir = Path(os.environ["TASK_DIR"]).resolve()
force_failfast = os.environ.get("FORCE_FAILFAST", "0") == "1"


def normalize_subject_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def subject_id_from_path(path: Path) -> str:
    text = path.name
    match = re.search(r"sub-[A-Za-z0-9_-]+", text)
    if match:
        return match.group(0)
    stem = path.stem
    if stem.endswith(".nii"):
        stem = stem[:-4]
    return stem.split("_")[0]


def candidate_input_dirs(dataset_id: str) -> list[Path]:
    env_input = os.environ.get("INPUT_DIR", "").strip()
    candidates = []
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

    uniq = []
    seen = set()
    for path in candidates:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(path)
    return uniq


def resolve_best_input_root(dataset_id: str) -> tuple[Path | None, list[Path], list[Path]]:
    checked = candidate_input_dirs(dataset_id)
    existing = [p for p in checked if p.exists() and p.is_dir()]
    if not existing:
        return None, checked, []

    # If INPUT_DIR is provided by runner, trust it first and avoid scanning broad roots
    # (e.g., /task/cache can contain very large unrelated trees and cause timeouts).
    env_input = os.environ.get("INPUT_DIR", "").strip()
    if env_input:
        env_path = Path(env_input)
        env_candidates = [env_path, env_path / dataset_id]
        for root in env_candidates:
            if root.exists() and root.is_dir():
                files = [p for p in root.rglob("*") if p.is_file()]
                if files:
                    return root, checked, files

    best_root = None
    best_files = []
    for root in existing:
        # Favor dataset-specific roots; avoid preferring massive generic caches.
        root_key = root.as_posix().lower()
        has_dataset_hint = dataset_id.lower() in root_key or "lesion" in root_key or "symptom" in root_key
        files = [p for p in root.rglob("*") if p.is_file()]
        if not best_root:
            best_root = root
            best_files = files
            continue
        best_key = best_root.as_posix().lower()
        best_has_hint = dataset_id.lower() in best_key or "lesion" in best_key or "symptom" in best_key
        if has_dataset_hint and not best_has_hint:
            best_root = root
            best_files = files
            continue
        if has_dataset_hint == best_has_hint and len(files) > len(best_files):
            best_root = root
            best_files = files
    return best_root, checked, best_files


def write_failfast(reason: str, checked_paths: list[Path], data_root: Path | None = None) -> None:
    fail_img = nib.Nifti1Image(np.zeros((4, 4, 4), dtype=np.float32), affine=np.eye(4))
    nib.save(fail_img, str(output_dir / "vlsm_map.nii.gz"))

    with (output_dir / "deficit_correlations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "voxel_index",
                "x",
                "y",
                "z",
                "correlation_r",
                "t_stat",
                "p_value",
                "n_subjects",
                "status",
                "reason",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "voxel_index": -1,
                "x": -1,
                "y": -1,
                "z": -1,
                "correlation_r": 0.0,
                "t_stat": 0.0,
                "p_value": 1.0,
                "n_subjects": 0,
                "status": "failed_precondition",
                "reason": reason,
            }
        )

    run_meta = {
        "task_id": TASK_ID,
        "dataset_source": DATASET_SOURCE,
        "dataset_id": DATASET_ID,
        "status": "failed_precondition",
        "reason": reason,
        "data_root": str(data_root) if data_root else "",
        "checked_paths": [str(p) for p in checked_paths],
        "n_subjects_used": 0,
        "n_voxels_tested": 0,
        "n_rows_reported": 1,
    }
    (output_dir / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")
    print(f"Fail-fast: {reason}")


def pick_behavior_table(paths: list[Path]) -> Path | None:
    tab_candidates = [p for p in paths if p.suffix.lower() in {".csv", ".tsv"}]
    if not tab_candidates:
        return None

    def score(path: Path) -> tuple[int, int]:
        lower = path.name.lower()
        keyword_score = int(any(k in lower for k in ["deficit", "symptom", "behavior", "score"]))
        return (keyword_score, path.stat().st_size)

    tab_candidates.sort(key=score, reverse=True)
    return tab_candidates[0]


def load_behavior(table_path: Path):
    sep = "\t" if table_path.suffix.lower() == ".tsv" else ","
    df = pd.read_csv(table_path, sep=sep)
    if df.empty:
        return None

    cols = list(df.columns)
    subject_candidates = [
        c
        for c in cols
        if c.lower() in {"subject_id", "participant_id", "sub_id", "subject", "participant", "id"}
        or "subject" in c.lower()
        or "participant" in c.lower()
    ]
    subject_col = subject_candidates[0] if subject_candidates else cols[0]

    numeric_cols = [c for c in cols if c != subject_col and pd.api.types.is_numeric_dtype(df[c])]
    if not numeric_cols:
        return None

    deficit_candidates = [
        c
        for c in numeric_cols
        if any(k in c.lower() for k in ["deficit", "symptom", "behavior", "score", "severity", "outcome"])
    ]
    deficit_col = deficit_candidates[0] if deficit_candidates else numeric_cols[0]

    out = {}
    for _, row in df[[subject_col, deficit_col]].dropna().iterrows():
        sid = str(row[subject_col]).strip()
        key = normalize_subject_id(sid)
        out[key] = (sid, float(row[deficit_col]))

    if len(out) < 4:
        return None
    return subject_col, deficit_col, out


def lesion_candidates(paths: list[Path]) -> list[Path]:
    nii = [
        p
        for p in paths
        if p.name.lower().endswith(".nii") or p.name.lower().endswith(".nii.gz")
    ]
    if not nii:
        return []

    lesion_pref = [p for p in nii if any(k in p.name.lower() for k in ["lesion", "mask", "stroke", "infarct"])]
    return lesion_pref if lesion_pref else nii


root, checked_paths, all_files = resolve_best_input_root(DATASET_ID)
if force_failfast:
    write_failfast("forced_failfast", checked_paths, data_root=root)
    raise SystemExit(0)
if root is None or not all_files:
    write_failfast("missing_input_dir_or_empty", checked_paths, data_root=root)
    raise SystemExit(0)

behavior_path = pick_behavior_table(all_files)
if behavior_path is None:
    write_failfast("missing_behavior_table", checked_paths, data_root=root)
    raise SystemExit(0)

behavior = load_behavior(behavior_path)
if behavior is None:
    write_failfast("invalid_behavior_table", checked_paths, data_root=root)
    raise SystemExit(0)

subject_col, deficit_col, behavior_map = behavior
lesion_paths = lesion_candidates(all_files)
if len(lesion_paths) < 4:
    write_failfast("insufficient_lesion_maps", checked_paths, data_root=root)
    raise SystemExit(0)

matched = []
for path in sorted(lesion_paths):
    sid_text = subject_id_from_path(path)
    key = normalize_subject_id(sid_text)
    if key in behavior_map:
        matched.append((path, behavior_map[key][0], behavior_map[key][1]))

if len(matched) < 4:
    # fallback: order-based pairing for datasets without id-consistent filenames
    sorted_lesions = sorted(lesion_paths)
    sorted_behavior = sorted(behavior_map.items(), key=lambda x: x[0])
    n = min(len(sorted_lesions), len(sorted_behavior))
    matched = []
    for i in range(n):
        path = sorted_lesions[i]
        orig_id, deficit = sorted_behavior[i][1]
        matched.append((path, orig_id, deficit))

if len(matched) < 4:
    write_failfast("insufficient_matched_subjects", checked_paths, data_root=root)
    raise SystemExit(0)

# Load lesion maps and build matrix.
first_img = nib.load(str(matched[0][0]))
first_arr = np.asarray(first_img.get_fdata(), dtype=float)
if first_arr.ndim > 3:
    first_arr = first_arr[..., 0]
shape = first_arr.shape
affine = first_img.affine

subject_ids = []
deficits = []
flat_maps = []
used_paths = []

for path, sid, deficit in matched:
    img = nib.load(str(path))
    arr = np.asarray(img.get_fdata(), dtype=float)
    if arr.ndim > 3:
        arr = arr[..., 0]
    if arr.shape != shape:
        continue

    lesion = (arr > 0).astype(np.float32)
    flat_maps.append(lesion.reshape(-1))
    subject_ids.append(sid)
    deficits.append(float(deficit))
    used_paths.append(str(path))

if len(flat_maps) < 4:
    write_failfast("insufficient_consistent_lesion_shapes", checked_paths, data_root=root)
    raise SystemExit(0)

X = np.stack(flat_maps, axis=0)
y = np.asarray(deficits, dtype=float)

var = np.var(X, axis=0)
valid = np.where(var > 0)[0]
if valid.size < 10:
    write_failfast("too_few_variable_voxels", checked_paths, data_root=root)
    raise SystemExit(0)

max_voxels = 30000
if valid.size > max_voxels:
    idx_sorted = valid[np.argsort(var[valid])[::-1]]
    selected = idx_sorted[:max_voxels]
else:
    selected = valid

Xs = X[:, selected]
yc = y - np.mean(y)
xc = Xs - np.mean(Xs, axis=0, keepdims=True)

den = np.sqrt(np.sum(xc * xc, axis=0) * np.sum(yc * yc)) + 1e-12
r = np.sum(xc * yc[:, None], axis=0) / den
r = np.clip(r, -1.0, 1.0)

df = max(1, len(y) - 2)
t_stat = r * np.sqrt(df / np.maximum(1.0 - r * r, 1e-12))
p_values = 2.0 * stats.t.sf(np.abs(t_stat), df=df)
p_values = np.clip(p_values, 0.0, 1.0)

order = np.lexsort((selected, -np.abs(r), p_values))
keep = order[:200]

map_flat = np.zeros(np.prod(shape), dtype=np.float32)
map_flat[selected] = r.astype(np.float32)
map_arr = map_flat.reshape(shape)

nib.save(nib.Nifti1Image(map_arr, affine=affine), str(output_dir / "vlsm_map.nii.gz"))

with (output_dir / "deficit_correlations.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=[
            "voxel_index",
            "x",
            "y",
            "z",
            "correlation_r",
            "t_stat",
            "p_value",
            "n_subjects",
            "status",
            "reason",
        ],
    )
    writer.writeheader()
    for idx in keep.tolist():
        flat_idx = int(selected[idx])
        x, yv, z = np.unravel_index(flat_idx, shape)
        writer.writerow(
            {
                "voxel_index": flat_idx,
                "x": int(x),
                "y": int(yv),
                "z": int(z),
                "correlation_r": float(r[idx]),
                "t_stat": float(t_stat[idx]),
                "p_value": float(p_values[idx]),
                "n_subjects": int(len(subject_ids)),
                "status": "ok",
                "reason": "computed",
            }
        )

run_meta = {
    "task_id": TASK_ID,
    "dataset_source": DATASET_SOURCE,
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "data_root": str(root),
    "checked_paths": [str(p) for p in checked_paths],
    "behavior_table": str(behavior_path),
    "behavior_subject_column": subject_col,
    "behavior_deficit_column": deficit_col,
    "n_subjects_used": int(len(subject_ids)),
    "used_subject_ids": subject_ids,
    "used_file_paths": used_paths,
    "n_voxels_tested": int(len(selected)),
    "n_rows_reported": int(len(keep)),
    "n_permutations": 0,
    "pvalue_method": "two_sided_t_distribution",
}
(output_dir / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")

print(f"Wrote outputs to {output_dir}")
print(f"subjects={len(subject_ids)} voxels={len(selected)} rows={len(keep)}")
