import csv
import json
import os
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from nilearn import datasets, surface

TASK_ID = "CONN-002"
DATASET_ID = "fetch_surf_nki_enhanced"
NETWORK_LABELS = {
    1: "Visual",
    2: "Somatomotor",
    3: "DorsalAttention",
    4: "VentralAttention",
    5: "Limbic",
    6: "Frontoparietal",
    7: "Default",
}

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


def write_timeseries(rows: list[dict]) -> None:
    with (output_dir / "network_timeseries.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["subject_id", "timepoint", "network_id", "network_label", "signal"],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_corr_png(corr: np.ndarray, title: str) -> None:
    fig, ax = plt.subplots(figsize=(6, 5), dpi=120)
    im = ax.imshow(corr, vmin=-1.0, vmax=1.0, cmap="coolwarm")
    ax.set_xticks(range(7))
    ax.set_yticks(range(7))
    ax.set_xticklabels([NETWORK_LABELS[i] for i in range(1, 8)], rotation=45, ha="right")
    ax.set_yticklabels([NETWORK_LABELS[i] for i in range(1, 8)])
    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(output_dir / "correlation_matrix.png")
    plt.close(fig)


def write_failfast(reason: str) -> None:
    rows = []
    for nid in range(1, 8):
        rows.append(
            {
                "subject_id": "sub-failed",
                "timepoint": 0,
                "network_id": nid,
                "network_label": NETWORK_LABELS[nid],
                "signal": 0.0,
            }
        )
    write_timeseries(rows)
    write_corr_png(np.eye(7, dtype=float), "Fail-fast correlation preview")
    write_metadata(
        {
            "task_id": TASK_ID,
            "dataset_source": "Nilearn",
            "dataset_id": DATASET_ID,
            "status": "failed_precondition",
            "reason": reason,
            "used_subject_ids": [],
            "n_rows_network_timeseries": len(rows),
            "n_networks": 7,
            "correlation_matrix_shape": [7, 7],
            "correlation_upper_mean": 0.0,
        }
    )


if force_failfast:
    write_failfast("forced_failfast")
    raise SystemExit(0)


def normalize_surface_data(data: np.ndarray, expected_vertices: int) -> np.ndarray:
    arr = np.asarray(data, dtype=float)
    if arr.ndim != 2:
        raise RuntimeError(f"invalid_surface_shape_{arr.shape}")
    if arr.shape[0] == expected_vertices:
        return arr
    if arr.shape[1] == expected_vertices:
        return arr.T
    raise RuntimeError(
        f"surface_vertex_mismatch_expected_{expected_vertices}_got_{arr.shape}"
    )


try:
    nki = datasets.fetch_surf_nki_enhanced(
        n_subjects=5,
        data_dir=str(cache_dir),
        verbose=0,
    )
    if len(nki.func_left) < 3 or len(nki.func_right) < 3:
        raise RuntimeError("insufficient_nki_subjects")

    atlas = datasets.fetch_atlas_yeo_2011(
        n_networks=7,
        thickness="thick",
        data_dir=str(cache_dir / "atlas_yeo"),
    )
    fsavg = datasets.fetch_surf_fsaverage(mesh="fsaverage5", data_dir=str(cache_dir / "fsaverage"))

    yeo_maps = atlas["maps"] if "maps" in atlas else atlas["thick_7"]
    labels_left = surface.vol_to_surf(
        yeo_maps,
        fsavg.pial_left,
        interpolation="nearest_most_frequent",
    )
    labels_right = surface.vol_to_surf(
        yeo_maps,
        fsavg.pial_right,
        interpolation="nearest_most_frequent",
    )
    labels_left = np.round(np.asarray(labels_left).squeeze()).astype(int)
    labels_right = np.round(np.asarray(labels_right).squeeze()).astype(int)

    n_vertices_left = int(labels_left.shape[0])
    n_vertices_right = int(labels_right.shape[0])

    network_vertex_counts = {}
    for network_id in range(1, 8):
        network_vertex_counts[str(network_id)] = int(
            np.sum(labels_left == network_id) + np.sum(labels_right == network_id)
        )
        if network_vertex_counts[str(network_id)] == 0:
            raise RuntimeError(f"network_{network_id}_empty_vertex_projection")

    subject_mats = []
    network_rows = []
    used_subject_ids = []

    for left_path, right_path in zip(nki.func_left, nki.func_right):
        subject_id = Path(left_path).name.split("_")[0]
        left_data = normalize_surface_data(surface.load_surf_data(left_path), n_vertices_left)
        right_data = normalize_surface_data(surface.load_surf_data(right_path), n_vertices_right)

        n_timepoints = min(left_data.shape[1], right_data.shape[1])
        if n_timepoints < 50:
            continue

        left_data = left_data[:, :n_timepoints]
        right_data = right_data[:, :n_timepoints]

        subject_network_signals = np.zeros((n_timepoints, 7), dtype=float)

        for network_id in range(1, 8):
            left_mask = labels_left == network_id
            right_mask = labels_right == network_id

            combined = np.concatenate(
                [left_data[left_mask, :], right_data[right_mask, :]],
                axis=0,
            )
            if combined.size == 0:
                raise RuntimeError(f"network_{network_id}_empty_subject_{subject_id}")
            signal = np.mean(combined, axis=0)
            subject_network_signals[:, network_id - 1] = signal

            for timepoint, value in enumerate(signal.tolist()):
                network_rows.append(
                    {
                        "subject_id": subject_id,
                        "timepoint": timepoint,
                        "network_id": network_id,
                        "network_label": NETWORK_LABELS[network_id],
                        "signal": float(value),
                    }
                )

        corr = np.corrcoef(subject_network_signals, rowvar=False)
        np.fill_diagonal(corr, 1.0)
        subject_mats.append(corr)
        used_subject_ids.append(subject_id)

    if len(subject_mats) < 3:
        raise RuntimeError("insufficient_valid_subjects_after_filtering")

    mean_corr = np.mean(np.stack(subject_mats, axis=0), axis=0)
    mean_corr = (mean_corr + mean_corr.T) / 2.0
    np.fill_diagonal(mean_corr, 1.0)

    write_timeseries(network_rows)
    write_corr_png(mean_corr, "NKI Yeo-7 Network Correlation")

    write_metadata(
        {
            "task_id": TASK_ID,
            "dataset_source": "Nilearn",
            "dataset_id": DATASET_ID,
            "status": "ok",
            "reason": "computed",
            "n_subjects": int(len(used_subject_ids)),
            "used_subject_ids": sorted(used_subject_ids),
            "n_rows_network_timeseries": int(len(network_rows)),
            "n_networks": 7,
            "network_vertex_counts": network_vertex_counts,
            "correlation_matrix_shape": [int(x) for x in mean_corr.shape],
            "correlation_upper_mean": float(np.mean(mean_corr[np.triu_indices_from(mean_corr, k=1)])),
            "cache_dir": str(cache_dir),
        }
    )

    print(f"Wrote outputs to {output_dir}")
    print(f"subjects={len(used_subject_ids)} rows={len(network_rows)}")
except Exception as exc:
    reason = safe_reason(exc)
    write_failfast(reason)
    print(f"failed_precondition: {reason}")
