import json
import os
import pickle
import re
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd

TASK_ID = "CLIN-014"
DATASET_SOURCE = "Provided"
DATASET_ID = "simulated_treatment_dataset"

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

    best_root = None
    best_files = []
    for root in existing:
        files = [p for p in root.rglob("*") if p.is_file()]
        if len(files) > len(best_files):
            best_root = root
            best_files = files
    return best_root, checked, best_files


def write_failfast(reason: str, checked_paths: list[Path], data_root: Path | None = None) -> None:
    model = {
        "task_id": TASK_ID,
        "dataset_source": DATASET_SOURCE,
        "dataset_id": DATASET_ID,
        "status": "failed_precondition",
        "reason": reason,
    }
    with (output_dir / "responder_model.pkl").open("wb") as handle:
        pickle.dump(model, handle)

    fail_img = nib.Nifti1Image(np.zeros((4, 4, 4), dtype=np.float32), affine=np.eye(4))
    nib.save(fail_img, str(output_dir / "predictive_map.nii.gz"))

    run_meta = {
        "task_id": TASK_ID,
        "dataset_source": DATASET_SOURCE,
        "dataset_id": DATASET_ID,
        "status": "failed_precondition",
        "reason": reason,
        "data_root": str(data_root) if data_root else "",
        "checked_paths": [str(p) for p in checked_paths],
        "n_subjects_used": 0,
        "n_subjects_responder": 0,
        "n_subjects_non_responder": 0,
    }
    (output_dir / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")
    print(f"Fail-fast: {reason}")


def parse_binary_label(value):
    if isinstance(value, (int, np.integer, float, np.floating)):
        if np.isnan(value):
            return None
        if int(value) in (0, 1):
            return int(value)
        return None

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "responder", "response", "responded"}:
        return 1
    if text in {"0", "false", "no", "n", "nonresponder", "non_responder", "non-response", "nonresponse"}:
        return 0
    return None


def pick_label_table(paths: list[Path]):
    tables = [p for p in paths if p.suffix.lower() in {".csv", ".tsv"}]
    if not tables:
        return None

    def table_score(path: Path) -> tuple[int, int]:
        lower = path.name.lower()
        keyword = int(any(k in lower for k in ["response", "responder", "outcome", "label", "target"]))
        return (keyword, path.stat().st_size)

    for table_path in sorted(tables, key=table_score, reverse=True):
        sep = "\t" if table_path.suffix.lower() == ".tsv" else ","
        try:
            df = pd.read_csv(table_path, sep=sep)
        except Exception:
            continue
        if df.empty:
            continue

        cols = list(df.columns)
        subject_candidates = [
            c
            for c in cols
            if c.lower() in {"subject_id", "participant_id", "sub_id", "subject", "participant", "id"}
            or "subject" in c.lower()
            or "participant" in c.lower()
        ]
        subject_col = subject_candidates[0] if subject_candidates else cols[0]

        label_col = None
        preferred = [
            c
            for c in cols
            if c != subject_col and any(k in c.lower() for k in ["responder", "response", "outcome", "label", "target"])
        ]
        if preferred:
            label_col = preferred[0]
        else:
            for c in cols:
                if c == subject_col:
                    continue
                vals = [parse_binary_label(v) for v in df[c].tolist()]
                vals = [v for v in vals if v is not None]
                uniq = sorted(set(vals))
                if uniq in ([0], [1], [0, 1]):
                    label_col = c
                    break

        if label_col is None:
            continue

        out = {}
        for _, row in df[[subject_col, label_col]].iterrows():
            sid = str(row[subject_col]).strip()
            if not sid:
                continue
            label = parse_binary_label(row[label_col])
            if label is None:
                continue
            out[normalize_subject_id(sid)] = (sid, int(label))

        labels = [v[1] for v in out.values()]
        if len(out) >= 6 and len(set(labels)) == 2:
            return table_path, subject_col, label_col, out

    return None


def nifti_candidates(paths: list[Path]) -> list[Path]:
    nii = [p for p in paths if p.name.lower().endswith(".nii") or p.name.lower().endswith(".nii.gz")]
    if not nii:
        return []
    preferred = [p for p in nii if any(k in p.name.lower() for k in ["baseline", "t1", "anat", "struct"])]
    return preferred if preferred else nii


def map_features(arr: np.ndarray) -> np.ndarray:
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        raise RuntimeError("No finite values in baseline image")
    nz = finite[np.abs(finite) > 1e-12]
    if nz.size == 0:
        nz = finite
    return np.array(
        [
            float(np.mean(finite)),
            float(np.std(finite)),
            float(np.percentile(nz, 10)),
            float(np.percentile(nz, 50)),
            float(np.percentile(nz, 90)),
            float(np.mean(np.abs(finite) > 1e-12)),
        ],
        dtype=float,
    )


def sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def fit_logistic_regression(X: np.ndarray, y: np.ndarray):
    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma == 0.0] = 1.0
    Xn = (X - mu) / sigma

    w = np.zeros(Xn.shape[1], dtype=float)
    b = 0.0
    lr = 0.1
    l2 = 1e-3

    for _ in range(2500):
        z = Xn @ w + b
        p = sigmoid(z)
        grad_w = (Xn.T @ (p - y)) / len(y) + l2 * w
        grad_b = float(np.mean(p - y))
        w -= lr * grad_w
        b -= lr * grad_b

    return mu, sigma, w, b


def predict_proba(X: np.ndarray, mu: np.ndarray, sigma: np.ndarray, w: np.ndarray, b: float) -> np.ndarray:
    Xn = (X - mu) / sigma
    return sigmoid(Xn @ w + b)


def auc_score(y_true: np.ndarray, scores: np.ndarray) -> float:
    y_true = np.asarray(y_true, dtype=int)
    scores = np.asarray(scores, dtype=float)
    n_pos = int(np.sum(y_true == 1))
    n_neg = int(np.sum(y_true == 0))
    if n_pos == 0 or n_neg == 0:
        return 0.5
    ranks = np.argsort(np.argsort(scores)) + 1
    sum_ranks_pos = float(np.sum(ranks[y_true == 1]))
    auc = (sum_ranks_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


root, checked_paths, all_files = resolve_best_input_root(DATASET_ID)
if force_failfast:
    write_failfast("forced_failfast", checked_paths, data_root=root)
    raise SystemExit(0)
if root is None or not all_files:
    write_failfast("missing_input_dir_or_empty", checked_paths, data_root=root)
    raise SystemExit(0)

label_info = pick_label_table(all_files)
if label_info is None:
    write_failfast("missing_or_invalid_label_table", checked_paths, data_root=root)
    raise SystemExit(0)

label_table, subject_col, label_col, label_map = label_info
image_paths = nifti_candidates(all_files)
if len(image_paths) < 6:
    write_failfast("insufficient_baseline_nifti", checked_paths, data_root=root)
    raise SystemExit(0)

matched = []
for path in sorted(image_paths):
    sid_text = subject_id_from_path(path)
    key = normalize_subject_id(sid_text)
    if key in label_map:
        sid, label = label_map[key]
        matched.append((path, sid, int(label)))

if len(matched) < 6:
    write_failfast("insufficient_matched_subjects", checked_paths, data_root=root)
    raise SystemExit(0)

first_img = nib.load(str(matched[0][0]))
first_arr = np.asarray(first_img.get_fdata(), dtype=float)
if first_arr.ndim > 3:
    first_arr = first_arr[..., 0]
shape = first_arr.shape
affine = first_img.affine

subject_ids = []
labels = []
features = []
maps = []
used_paths = []

for path, sid, label in matched:
    img = nib.load(str(path))
    arr = np.asarray(img.get_fdata(), dtype=float)
    if arr.ndim > 3:
        arr = arr[..., 0]
    if arr.shape != shape:
        continue

    subject_ids.append(sid)
    labels.append(int(label))
    features.append(map_features(arr))
    maps.append(arr.astype(np.float32))
    used_paths.append(str(path))

if len(subject_ids) < 6:
    write_failfast("insufficient_consistent_image_shapes", checked_paths, data_root=root)
    raise SystemExit(0)

labels_arr = np.asarray(labels, dtype=int)
if len(set(labels_arr.tolist())) < 2:
    write_failfast("single_class_labels", checked_paths, data_root=root)
    raise SystemExit(0)

n_resp = int(np.sum(labels_arr == 1))
n_non = int(np.sum(labels_arr == 0))
if n_resp < 2 or n_non < 2:
    write_failfast("insufficient_class_counts", checked_paths, data_root=root)
    raise SystemExit(0)

X = np.stack(features, axis=0)
mu, sigma, w, b = fit_logistic_regression(X, labels_arr.astype(float))
proba = predict_proba(X, mu, sigma, w, b)
pred = (proba >= 0.5).astype(int)
accuracy = float(np.mean(pred == labels_arr))
auc = auc_score(labels_arr, proba)

responder_maps = [maps[i] for i in range(len(maps)) if labels_arr[i] == 1]
non_maps = [maps[i] for i in range(len(maps)) if labels_arr[i] == 0]
mean_responder = np.mean(np.stack(responder_maps, axis=0), axis=0)
mean_non = np.mean(np.stack(non_maps, axis=0), axis=0)
predictive_map = (mean_responder - mean_non).astype(np.float32)

nib.save(nib.Nifti1Image(predictive_map, affine=affine), str(output_dir / "predictive_map.nii.gz"))
saved_map = np.asarray(nib.load(str(output_dir / "predictive_map.nii.gz")).get_fdata(), dtype=float)

model = {
    "task_id": TASK_ID,
    "dataset_source": DATASET_SOURCE,
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "feature_names": [
        "mean_intensity",
        "std_intensity",
        "p10_intensity",
        "p50_intensity",
        "p90_intensity",
        "nonzero_fraction",
    ],
    "feature_mu": mu.tolist(),
    "feature_sigma": sigma.tolist(),
    "weights": w.tolist(),
    "intercept": float(b),
    "train_accuracy": accuracy,
    "train_auc": auc,
    "label_subject_column": subject_col,
    "label_target_column": label_col,
    "n_subjects_used": int(len(subject_ids)),
    "class_counts": {"responder": n_resp, "non_responder": n_non},
}
with (output_dir / "responder_model.pkl").open("wb") as handle:
    pickle.dump(model, handle)

run_meta = {
    "task_id": TASK_ID,
    "dataset_source": DATASET_SOURCE,
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "data_root": str(root),
    "checked_paths": [str(p) for p in checked_paths],
    "label_table": str(label_table),
    "n_subjects_used": int(len(subject_ids)),
    "n_subjects_responder": n_resp,
    "n_subjects_non_responder": n_non,
    "used_subject_ids": subject_ids,
    "used_file_paths": used_paths,
    "train_accuracy": accuracy,
    "train_auc": auc,
    "predictive_map_mean": float(np.mean(saved_map)),
    "predictive_map_std": float(np.std(saved_map)),
}
(output_dir / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")

print(f"Wrote outputs to {output_dir}")
print(f"subjects={len(subject_ids)} responders={n_resp} non_responders={n_non}")
