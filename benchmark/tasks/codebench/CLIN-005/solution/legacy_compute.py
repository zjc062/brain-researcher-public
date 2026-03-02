import csv
import json
import os
import re
import traceback
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from nilearn import datasets

TASK_ID = "CLIN-005"
DATASET_SOURCE = "Nilearn"
DATASET_ID = "fetch_oasis_vbm"

output_dir = Path(os.environ["OUTPUT_DIR"]).resolve()
cache_dir = Path(os.environ["CACHE_DIR"]).resolve()
cache_dir.mkdir(parents=True, exist_ok=True)
force_failfast = os.environ.get("FORCE_FAILFAST", "0") == "1"


def subject_id_from_path(path: str) -> str:
    name = Path(path).name
    match = re.search(r"(OAS1_\d+_MR\d+)", name)
    if match:
        return match.group(1)
    return Path(path).stem


def render_failure_plot(path: Path, reason: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=120)
    ax.axis("off")
    ax.text(
        0.02,
        0.70,
        "CLIN-005 failed_precondition",
        fontsize=13,
        weight="bold",
        color="#9f1239",
        transform=ax.transAxes,
    )
    ax.text(
        0.02,
        0.48,
        f"reason: {reason}",
        fontsize=10,
        color="#334155",
        transform=ax.transAxes,
        wrap=True,
    )
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


run_meta = {
    "task_id": TASK_ID,
    "dataset_source": DATASET_SOURCE,
    "dataset_id": DATASET_ID,
    "status": "failed_precondition",
    "reason": "not_started",
    "n_subjects_total": 0,
    "n_subjects_train": 0,
    "n_subjects_test": 0,
    "brain_age_gap_mean": 0.0,
    "brain_age_gap_std": 0.0,
    "mae_train": 0.0,
    "mae_test": 0.0,
    "model_name": "oasis_feature_ridge_regression",
    "model_version": "v1",
    "model_source_type": "derived_from_input",
    "model_source": "oasis_vbm_intensity_features",
    "model_checkpoint_path": "",
    "inference_backend": "",
    "used_file_paths": [],
}

csv_path = output_dir / "predicted_ages.csv"
plot_path = output_dir / "age_gap_distribution.png"

try:
    if force_failfast:
        raise RuntimeError("forced_failfast")

    n_subjects = int(os.environ.get("N_SUBJECTS", "28"))
    shared_nilearn = os.environ.get("NILEARN_DATA_SHARED", "").strip()
    data_dir = cache_dir
    if shared_nilearn:
        shared_path = Path(shared_nilearn)
        if shared_path.exists() and shared_path.is_dir():
            data_dir = shared_path
    data = datasets.fetch_oasis_vbm(n_subjects=n_subjects, data_dir=str(data_dir), verbose=0)
    ext = data.ext_vars.copy()
    ext["id"] = ext["id"].astype(str)
    ext["age"] = np.asarray(ext["age"], dtype=float)

    age_by_subject = {row["id"]: float(row["age"]) for _, row in ext.iterrows()}

    rows = []
    for img_path in data.gray_matter_maps:
        sid = subject_id_from_path(img_path)
        if sid in age_by_subject:
            rows.append((sid, str(img_path), age_by_subject[sid]))

    if len(rows) < 20:
        raise RuntimeError("insufficient_subjects_after_oasis_matching")

    rows = sorted(rows, key=lambda x: x[0])
    subject_ids = [r[0] for r in rows]
    input_paths = [r[1] for r in rows]
    ages = np.asarray([r[2] for r in rows], dtype=float)

    # Real lightweight compute: derive robust intensity features from each OASIS map
    # and fit a ridge-regularized linear model on train split.
    feats = []
    kept_subject_ids = []
    kept_input_paths = []
    kept_ages = []
    for sid, p, age in rows:
        img = nib.load(p)
        arr = np.asarray(img.get_fdata(), dtype=np.float32)
        vals = arr[np.isfinite(arr)]
        if vals.size < 1000:
            continue
        feat = [
            float(np.mean(vals)),
            float(np.std(vals)),
            float(np.percentile(vals, 10.0)),
            float(np.percentile(vals, 50.0)),
            float(np.percentile(vals, 90.0)),
            float(np.mean(np.abs(vals))),
            float(np.mean(vals > np.mean(vals))),
        ]
        feats.append(feat)
        kept_subject_ids.append(sid)
        kept_input_paths.append(p)
        kept_ages.append(float(age))

    if len(feats) < 20:
        raise RuntimeError("insufficient_subjects_after_feature_extraction")

    subject_ids = kept_subject_ids
    input_paths = kept_input_paths
    ages = np.asarray(kept_ages, dtype=float)
    X = np.asarray(feats, dtype=np.float64)

    idx = np.arange(len(subject_ids), dtype=int)
    n_train = max(10, int(round(0.8 * len(idx))))
    train_idx = idx[:n_train]
    test_idx = idx[n_train:]
    if len(test_idx) == 0:
        test_idx = train_idx[-2:]
        train_idx = train_idx[:-2]
    split_map = {int(i): "train" for i in train_idx.tolist()}
    split_map.update({int(i): "test" for i in test_idx.tolist()})

    mu = np.mean(X[train_idx], axis=0)
    sigma = np.std(X[train_idx], axis=0) + 1e-6
    Xn = (X - mu) / sigma
    Xtr = np.concatenate([np.ones((len(train_idx), 1)), Xn[train_idx]], axis=1)
    Xall = np.concatenate([np.ones((len(subject_ids), 1)), Xn], axis=1)
    ytr = ages[train_idx]

    lam = 1e-3
    reg = np.eye(Xtr.shape[1], dtype=np.float64)
    reg[0, 0] = 0.0
    w = np.linalg.solve(Xtr.T @ Xtr + lam * reg, Xtr.T @ ytr)
    predicted = np.clip(Xall @ w, 0.0, 120.0)
    brain_age_gap = predicted - ages

    run_meta["model_version"] = "v1"
    run_meta["model_source_type"] = "derived_from_input"
    run_meta["model_source"] = "oasis_vbm_intensity_features"
    run_meta["model_checkpoint_path"] = ""
    run_meta["inference_backend"] = "cpu"

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "subject_id",
                "chronological_age",
                "predicted_age",
                "brain_age_gap",
                "split",
            ],
        )
        writer.writeheader()
        for i, sid in enumerate(subject_ids):
            writer.writerow(
                {
                    "subject_id": sid,
                    "chronological_age": float(ages[i]),
                    "predicted_age": float(predicted[i]),
                    "brain_age_gap": float(brain_age_gap[i]),
                    "split": split_map.get(i, "train"),
                }
            )

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=120)
    ax.hist(brain_age_gap, bins=20, color="#3a7ca5", alpha=0.85, edgecolor="white")
    ax.axvline(
        float(np.mean(brain_age_gap)),
        color="#d62828",
        linestyle="--",
        linewidth=1.8,
        label="mean",
    )
    ax.set_xlabel("Brain age gap (predicted - chronological)")
    ax.set_ylabel("Count")
    ax.set_title("OASIS brain-age gap distribution (feature regression)")
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(plot_path)
    plt.close(fig)

    mae_train = float(np.mean(np.abs(predicted[train_idx] - ages[train_idx])))
    mae_test = float(np.mean(np.abs(predicted[test_idx] - ages[test_idx])))

    run_meta.update(
        {
            "status": "ok",
            "reason": "feature_regression_inference_ok",
            "n_subjects_total": int(len(subject_ids)),
            "n_subjects_train": int(len(train_idx)),
            "n_subjects_test": int(len(test_idx)),
            "brain_age_gap_mean": float(np.mean(brain_age_gap)),
            "brain_age_gap_std": float(np.std(brain_age_gap)),
            "mae_train": mae_train,
            "mae_test": mae_test,
            "used_file_paths": input_paths,
        }
    )
except Exception as exc:
    reason = f"{type(exc).__name__}:{exc}"
    run_meta["status"] = "failed_precondition"
    run_meta["reason"] = reason
    run_meta["traceback_tail"] = traceback.format_exc(limit=1)

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "subject_id",
                "chronological_age",
                "predicted_age",
                "brain_age_gap",
                "split",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "subject_id": "N/A",
                "chronological_age": 0.0,
                "predicted_age": 0.0,
                "brain_age_gap": 0.0,
                "split": "failed_precondition",
            }
        )

    render_failure_plot(plot_path, reason)

(output_dir / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")
print(f"Wrote outputs to {output_dir}")
print(f"status={run_meta['status']} reason={run_meta['reason']}")
