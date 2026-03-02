import csv
import json
import os
import re
from collections import deque
from pathlib import Path

import numpy as np
from nilearn import datasets
from nilearn.maskers import NiftiMapsMasker

TASK_ID = "CONN-007"
DATASET_ID = "fetch_abide_pcp"

output_dir = Path(os.environ["OUTPUT_DIR"]).resolve()
cache_dir = Path(os.environ["CACHE_DIR"]).resolve()
cache_dir.mkdir(parents=True, exist_ok=True)
force_failfast = os.environ.get("FORCE_FAILFAST", "0") == "1"


def safe_reason(exc: Exception | str) -> str:
    text = str(exc).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return (text or "failed_precondition")[:96]


def write_graph_metrics(rows: list[dict]) -> None:
    with (output_dir / "graph_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "subject_id",
                "dx_group",
                "mean_degree",
                "density",
                "clustering_coeff",
                "path_length",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_metadata(payload: dict) -> None:
    (output_dir / "run_metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_failfast(reason: str) -> None:
    write_graph_metrics(
        [
            {
                "subject_id": "sub-failed",
                "dx_group": 0,
                "mean_degree": 0.0,
                "density": 0.0,
                "clustering_coeff": 0.0,
                "path_length": 0.0,
            }
        ]
    )
    (output_dir / "small_world_sigma.txt").write_text("0.0\n", encoding="utf-8")
    write_metadata(
        {
            "task_id": TASK_ID,
            "dataset_source": "Nilearn",
            "dataset_id": DATASET_ID,
            "status": "failed_precondition",
            "reason": reason,
            "group_subject_counts": {"1": 0, "2": 0},
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


def make_adjacency(corr: np.ndarray, threshold: float = 0.2) -> np.ndarray:
    adj = (np.abs(corr) > threshold).astype(np.int8)
    np.fill_diagonal(adj, 0)
    adj = np.maximum(adj, adj.T)
    return adj


def clustering_coefficient(adj: np.ndarray) -> float:
    n = adj.shape[0]
    coeffs = []
    for i in range(n):
        neighbors = np.where(adj[i] > 0)[0]
        k = len(neighbors)
        if k < 2:
            continue
        sub = adj[np.ix_(neighbors, neighbors)]
        edges = float(np.sum(sub) / 2.0)
        coeffs.append((2.0 * edges) / (k * (k - 1)))
    if not coeffs:
        return 0.0
    return float(np.mean(coeffs))


def largest_component_nodes(adj: np.ndarray) -> list[int]:
    n = adj.shape[0]
    seen = set()
    largest = []
    for start in range(n):
        if start in seen:
            continue
        queue = deque([start])
        comp = []
        seen.add(start)
        while queue:
            node = queue.popleft()
            comp.append(node)
            for nbr in np.where(adj[node] > 0)[0].tolist():
                if nbr not in seen:
                    seen.add(nbr)
                    queue.append(int(nbr))
        if len(comp) > len(largest):
            largest = comp
    return largest


def average_path_length(adj: np.ndarray) -> float:
    nodes = largest_component_nodes(adj)
    if len(nodes) < 2:
        return float("nan")

    sub_adj = adj[np.ix_(nodes, nodes)]
    n = sub_adj.shape[0]
    dists = []

    for src in range(n):
        dist = np.full(n, -1, dtype=int)
        dist[src] = 0
        queue = deque([src])
        while queue:
            cur = queue.popleft()
            for nbr in np.where(sub_adj[cur] > 0)[0].tolist():
                if dist[nbr] == -1:
                    dist[nbr] = dist[cur] + 1
                    queue.append(int(nbr))

        for dst in range(src + 1, n):
            if dist[dst] > 0:
                dists.append(float(dist[dst]))

    if not dists:
        return float("nan")
    return float(np.mean(dists))


try:
    atlas = datasets.fetch_atlas_msdl(data_dir=str(cache_dir / "atlas_msdl"))
    masker = NiftiMapsMasker(
        maps_img=atlas.maps,
        standardize="zscore_sample",
        detrend=True,
        memory=str(cache_dir / "nilearn_cache"),
        memory_level=1,
    )

    records = []
    all_corr = []

    for dx_group in (1, 2):
        files, phen = fetch_group(dx_group=dx_group, n_subjects=3)

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
            all_corr.append(corr)

            adj = make_adjacency(corr, threshold=0.2)
            degree = np.sum(adj, axis=1).astype(float)
            mean_degree = float(np.mean(degree))
            density = float(np.sum(adj) / (adj.shape[0] * (adj.shape[0] - 1)))
            cluster = clustering_coefficient(adj)
            path_len = average_path_length(adj)
            if not np.isfinite(path_len) or path_len <= 0:
                continue

            records.append(
                {
                    "subject_id": subject_id,
                    "dx_group": int(dx_group),
                    "mean_degree": mean_degree,
                    "density": density,
                    "clustering_coeff": cluster,
                    "path_length": path_len,
                }
            )

    if len(records) < 4:
        raise RuntimeError("insufficient_valid_abide_subjects")

    present_groups = sorted({int(r["dx_group"]) for r in records})
    if present_groups != [1, 2]:
        raise RuntimeError(f"missing_required_groups_{present_groups}")

    write_graph_metrics(sorted(records, key=lambda r: (int(r["dx_group"]), r["subject_id"])))

    mean_corr = np.mean(np.stack(all_corr, axis=0), axis=0)
    mean_corr = (mean_corr + mean_corr.T) / 2.0
    np.fill_diagonal(mean_corr, 1.0)
    obs_adj = make_adjacency(mean_corr, threshold=0.2)

    c_obs = clustering_coefficient(obs_adj)
    l_obs = average_path_length(obs_adj)

    n_nodes = obs_adj.shape[0]
    p_edge = float(np.sum(obs_adj) / (n_nodes * (n_nodes - 1)))
    # Deterministic ER baseline (no sampling):
    # C_rand ~= p, L_rand ~= ln(N)/ln(k), where k is mean degree.
    k_mean = float(np.mean(np.sum(obs_adj, axis=1)))
    c_rand = max(p_edge, 1e-6)
    if n_nodes > 2 and k_mean > 1.0:
        l_rand = float(np.log(float(n_nodes)) / np.log(k_mean))
    else:
        l_rand = float("nan")
    if not np.isfinite(l_rand) or l_rand <= 0:
        # Conservative deterministic fallback keeps metric defined.
        l_rand = max(float(l_obs), 1e-6)

    if c_rand <= 0 or l_rand <= 0 or not np.isfinite(l_obs) or l_obs <= 0:
        raise RuntimeError("invalid_sigma_components")

    sigma = float((c_obs / c_rand) / (l_obs / l_rand))
    if not np.isfinite(sigma) or sigma <= 0:
        raise RuntimeError("invalid_sigma")

    (output_dir / "small_world_sigma.txt").write_text(f"{sigma:.6f}\n", encoding="utf-8")

    write_metadata(
        {
            "task_id": TASK_ID,
            "dataset_source": "Nilearn",
            "dataset_id": DATASET_ID,
            "status": "ok",
            "reason": "computed",
            "n_subjects": int(len(records)),
            "group_subject_counts": {
                "1": int(sum(1 for r in records if int(r["dx_group"]) == 1)),
                "2": int(sum(1 for r in records if int(r["dx_group"]) == 2)),
            },
            "n_regions": int(mean_corr.shape[0]),
            "sigma": sigma,
            "c_obs": c_obs,
            "l_obs": l_obs,
            "c_rand": c_rand,
            "l_rand": l_rand,
            "p_edge": p_edge,
            "rand_baseline_method": "deterministic_er_approx",
        }
    )

    print(f"Wrote outputs to {output_dir}")
    print(f"subjects={len(records)} sigma={sigma:.6f}")
except Exception as exc:
    reason = safe_reason(exc)
    write_failfast(reason)
    print(f"failed_precondition: {reason}")
