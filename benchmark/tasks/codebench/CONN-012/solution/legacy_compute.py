import csv
import json
import os
import re
from pathlib import Path

import numpy as np
from nilearn import datasets
from nilearn.maskers import NiftiMapsMasker
from scipy import stats

TASK_ID = "CONN-012"
DATASET_ID = "fetch_abide_pcp"

output_dir = Path(os.environ["OUTPUT_DIR"]).resolve()
cache_dir = Path(os.environ["CACHE_DIR"]).resolve()
cache_dir.mkdir(parents=True, exist_ok=True)
force_failfast = os.environ.get("FORCE_FAILFAST", "0") == "1"


def safe_reason(exc: Exception | str) -> str:
    text = str(exc).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return (text or "failed_precondition")[:96]


def write_metadata(payload: dict) -> None:
    (output_dir / "run_metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_edges_csv(rows: list[dict]) -> None:
    with (output_dir / "significant_edges.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "edge_i",
                "edge_j",
                "t_stat",
                "p_value",
                "mean_asd",
                "mean_control",
                "effect_size",
                "significant",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_failfast(reason: str) -> None:
    write_edges_csv(
        [
            {
                "edge_i": 0,
                "edge_j": 1,
                "t_stat": 0.0,
                "p_value": 1.0,
                "mean_asd": 0.0,
                "mean_control": 0.0,
                "effect_size": 0.0,
                "significant": 0,
            }
        ]
    )
    np.save(output_dir / "edge_statistics.npy", np.zeros((2, 2), dtype=float))
    write_metadata(
        {
            "task_id": TASK_ID,
            "dataset_source": "Nilearn",
            "dataset_id": DATASET_ID,
            "status": "failed_precondition",
            "reason": reason,
            "n_regions": 2,
            "used_subjects_asd": [],
            "used_subjects_control": [],
            "n_edges_total": 1,
            "n_significant": 0,
            "n_reported_edges": 1,
        }
    )


if force_failfast:
    write_failfast("forced_failfast")
    raise SystemExit(0)


def fetch_group(dx_group: int, n_subjects: int):
    abide = datasets.fetch_abide_pcp(
        data_dir=str(cache_dir),
        n_subjects=n_subjects,
        DX_GROUP=dx_group,
        verbose=0,
    )
    files = list(abide.func_preproc)
    phenotypic = abide.phenotypic
    if len(files) == 0 or len(phenotypic) == 0:
        raise RuntimeError(f"no_abide_data_for_group_{dx_group}")
    return files, phenotypic


try:
    atlas = datasets.fetch_atlas_msdl(data_dir=str(cache_dir / "atlas_msdl"))
    masker = NiftiMapsMasker(
        maps_img=atlas.maps,
        standardize="zscore_sample",
        detrend=True,
        memory=str(cache_dir / "nilearn_cache"),
        memory_level=1,
    )

    def compute_group_connectivity(dx_group: int, n_subjects: int):
        files, phen = fetch_group(dx_group=dx_group, n_subjects=n_subjects)
        mats = []
        subjects = []
        for fmri_path, (_, row) in zip(files, phen.iterrows()):
            sub_id = str(row.get("SUB_ID", "")).strip()
            if not sub_id:
                continue
            subject_id = f"sub-{sub_id}"

            ts = masker.fit_transform(fmri_path)
            if ts.ndim != 2 or ts.shape[0] < 20:
                continue

            corr = np.corrcoef(ts.T)
            np.fill_diagonal(corr, 1.0)
            mats.append(corr)
            subjects.append(subject_id)
        return subjects, mats

    subjects_asd, mats_asd = compute_group_connectivity(dx_group=1, n_subjects=4)
    subjects_ctl, mats_ctl = compute_group_connectivity(dx_group=2, n_subjects=4)

    if len(mats_asd) < 2 or len(mats_ctl) < 2:
        raise RuntimeError("insufficient_subjects_per_group")

    n_regions = mats_asd[0].shape[0]
    for mat in mats_asd + mats_ctl:
        if mat.shape[0] != n_regions or mat.shape[1] != n_regions:
            raise RuntimeError("inconsistent_connectivity_shapes")

    tri_i, tri_j = np.triu_indices(n_regions, k=1)

    def vectorize(mats):
        arr = np.stack(mats, axis=0)
        return arr[:, tri_i, tri_j]

    edges_asd = vectorize(mats_asd)
    edges_ctl = vectorize(mats_ctl)

    mean_asd = np.mean(edges_asd, axis=0)
    mean_ctl = np.mean(edges_ctl, axis=0)
    diff = mean_asd - mean_ctl

    var_asd = np.var(edges_asd, axis=0, ddof=1)
    var_ctl = np.var(edges_ctl, axis=0, ddof=1)

    se = np.sqrt(var_asd / edges_asd.shape[0] + var_ctl / edges_ctl.shape[0] + 1e-12)
    t_stat = diff / se
    pooled_std = np.sqrt((var_asd + var_ctl) / 2.0 + 1e-12)
    effect_size = diff / pooled_std

    # Deterministic Welch-Satterthwaite df + two-sided t p-values.
    n1 = edges_asd.shape[0]
    n2 = edges_ctl.shape[0]
    num = (var_asd / n1 + var_ctl / n2) ** 2
    den = (var_asd**2) / (max(n1 - 1, 1) * (n1**2)) + (var_ctl**2) / (max(n2 - 1, 1) * (n2**2)) + 1e-12
    df = np.maximum(num / den, 1.0)
    p_values = 2.0 * stats.t.sf(np.abs(t_stat), df=df)
    p_values = np.clip(p_values, 0.0, 1.0)
    significant = p_values < 0.05

    candidate_indices = np.where(significant)[0].tolist()
    if not candidate_indices:
        candidate_indices = np.argsort(p_values)[:10].tolist()

    rows = []
    for idx in candidate_indices:
        rows.append(
            {
                "edge_i": int(tri_i[idx]),
                "edge_j": int(tri_j[idx]),
                "t_stat": float(t_stat[idx]),
                "p_value": float(p_values[idx]),
                "mean_asd": float(mean_asd[idx]),
                "mean_control": float(mean_ctl[idx]),
                "effect_size": float(effect_size[idx]),
                "significant": int(bool(significant[idx])),
            }
        )

    rows.sort(key=lambda r: (r["p_value"], -abs(r["t_stat"]), r["edge_i"], r["edge_j"]))
    write_edges_csv(rows)

    stat_mat = np.zeros((n_regions, n_regions), dtype=float)
    stat_mat[tri_i, tri_j] = t_stat
    stat_mat[tri_j, tri_i] = t_stat
    np.fill_diagonal(stat_mat, 0.0)
    np.save(output_dir / "edge_statistics.npy", stat_mat)

    write_metadata(
        {
            "task_id": TASK_ID,
            "dataset_source": "Nilearn",
            "dataset_id": DATASET_ID,
            "status": "ok",
            "reason": "computed",
            "n_regions": int(n_regions),
            "n_subjects_asd": int(len(subjects_asd)),
            "n_subjects_control": int(len(subjects_ctl)),
            "used_subjects_asd": sorted(subjects_asd),
            "used_subjects_control": sorted(subjects_ctl),
            "n_edges_total": int(len(tri_i)),
            "n_significant": int(np.sum(significant)),
            "n_reported_edges": int(len(rows)),
            "n_permutations": 0,
            "pvalue_method": "welch_t_two_sided",
        }
    )

    print(f"Wrote outputs to {output_dir}")
    print(
        f"asd={len(subjects_asd)} control={len(subjects_ctl)} "
        f"significant={int(np.sum(significant))} reported={len(rows)}"
    )
except Exception as exc:
    reason = safe_reason(exc)
    write_failfast(reason)
    print(f"failed_precondition: {reason}")
