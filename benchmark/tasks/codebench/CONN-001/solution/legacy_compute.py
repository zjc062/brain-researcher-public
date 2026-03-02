import csv
import json
import os
import re
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from nilearn import datasets
from nilearn.maskers import NiftiMapsMasker

GRAPHQL_URL = "https://openneuro.org/crn/graphql"
DATASET_ID = "ds002424"
TASK_ID = "CONN-001"

output_dir = Path(os.environ["OUTPUT_DIR"]).resolve()
cache_dir = Path(os.environ["CACHE_DIR"]).resolve()
raw_dir = cache_dir / "raw"
raw_dir.mkdir(parents=True, exist_ok=True)
force_failfast = os.environ.get("FORCE_FAILFAST", "0") == "1"


def safe_reason(exc: Exception | str) -> str:
    text = str(exc).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return (text or "failed_precondition")[:96]


def write_group_csv(rows: list[dict]) -> None:
    with (output_dir / "group_comparison.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "group_label",
                "dx_group",
                "n_subjects",
                "mean_edge_connectivity",
                "std_edge_connectivity",
                "subject_ids",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_metadata(payload: dict) -> None:
    (output_dir / "run_metadata.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_failfast(reason: str) -> None:
    mat = np.eye(10, dtype=float)
    np.save(output_dir / "connectivity_matrix.npy", mat)
    write_group_csv(
        [
            {
                "group_label": "control",
                "dx_group": 0,
                "n_subjects": 0,
                "mean_edge_connectivity": 0.0,
                "std_edge_connectivity": 0.0,
                "subject_ids": "",
            },
            {
                "group_label": "adhd",
                "dx_group": 1,
                "n_subjects": 0,
                "mean_edge_connectivity": 0.0,
                "std_edge_connectivity": 0.0,
                "subject_ids": "",
            },
        ]
    )
    write_metadata(
        {
            "task_id": TASK_ID,
            "dataset_source": "OpenNeuro",
            "dataset_id": DATASET_ID,
            "status": "failed_precondition",
            "reason": reason,
            "used_subject_ids": [],
            "used_file_paths": [],
            "matrix_shape": [10, 10],
            "matrix_upper_mean": 0.0,
        }
    )


if force_failfast:
    write_failfast("forced_failfast")
    raise SystemExit(0)


def gql(query: str, variables: dict) -> dict:
    response = requests.post(
        GRAPHQL_URL,
        json={"query": query, "variables": variables},
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise RuntimeError(f"openneuro_graphql_error_{payload['errors'][0]}")
    return payload["data"]


def list_tree(tree_key: str | None) -> tuple[str, list[dict]]:
    query = """
    query SnapshotFiles($id: ID!, $tree: String) {
      dataset(id: $id) {
        latestSnapshot {
          tag
          files(tree: $tree) {
            key
            filename
            size
            directory
            urls
          }
        }
      }
    }
    """
    data = gql(query, {"id": DATASET_ID, "tree": tree_key})
    snap = data["dataset"]["latestSnapshot"]
    if snap is None:
        raise RuntimeError("openneuro_missing_latest_snapshot")
    return snap["tag"], snap["files"]


def download_file(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    with requests.get(url, stream=True, timeout=180) as response:
        response.raise_for_status()
        with dest.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)


try:
    snapshot_tag, root_files = list_tree(None)
    participants_entry = next(
        (node for node in root_files if node.get("filename") == "participants.tsv"),
        None,
    )
    if not participants_entry or not participants_entry.get("urls"):
        raise RuntimeError("missing_participants_tsv")

    participants_url = participants_entry["urls"][0]
    participants = pd.read_csv(participants_url, sep="\t")
    required_participant_columns = {"participant_id", "ADHD_diagnosis"}
    missing = required_participant_columns - set(participants.columns)
    if missing:
        raise RuntimeError(f"participants_missing_columns_{'_'.join(sorted(missing))}")

    participants = participants[["participant_id", "ADHD_diagnosis"]].copy()
    participants["participant_id"] = participants["participant_id"].astype(str)
    participants["ADHD_diagnosis"] = pd.to_numeric(
        participants["ADHD_diagnosis"], errors="coerce"
    ).astype("Int64")
    participants = participants.dropna(subset=["ADHD_diagnosis"])
    participants["ADHD_diagnosis"] = participants["ADHD_diagnosis"].astype(int)

    bold_by_subject: dict[str, list[tuple[str, str]]] = {}
    sub_dirs = [
        node
        for node in root_files
        if bool(node.get("directory")) and str(node.get("filename", "")).startswith("sub-")
    ]
    queue: deque[dict] = deque(sub_dirs)
    seen_keys: set[str] = set()
    subject_regex = re.compile(r"(sub-[A-Za-z0-9]+)")

    while queue:
        directory = queue.popleft()
        key = directory.get("key")
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)

        _, children = list_tree(key)
        for node in children:
            if node.get("directory"):
                queue.append(node)
                continue

            filename = str(node.get("filename", ""))
            if not filename.endswith("_bold.nii.gz"):
                continue
            urls = node.get("urls") or []
            if not urls:
                continue

            match = subject_regex.search(filename)
            if not match:
                continue
            subject_id = match.group(1)
            bold_by_subject.setdefault(subject_id, []).append((filename, urls[0]))

    if not bold_by_subject:
        raise RuntimeError("no_bold_files_found")

    participants = participants[participants["participant_id"].isin(bold_by_subject)].copy()
    if participants.empty:
        raise RuntimeError("participants_bold_overlap_empty")

    control_subjects = sorted(
        participants.loc[participants["ADHD_diagnosis"] == 0, "participant_id"].unique().tolist()
    )
    adhd_subjects = sorted(
        participants.loc[participants["ADHD_diagnosis"] == 1, "participant_id"].unique().tolist()
    )
    if not control_subjects or not adhd_subjects:
        raise RuntimeError("missing_required_dx_groups")

    selected_subjects = {
        0: control_subjects[:2],
        1: adhd_subjects[:2],
    }

    selected_records: list[dict] = []
    for dx_group, subject_ids in selected_subjects.items():
        for subject_id in subject_ids:
            candidates = sorted(bold_by_subject[subject_id], key=lambda item: item[0])
            filename, url = candidates[0]
            local_path = raw_dir / filename
            download_file(url, local_path)
            selected_records.append(
                {
                    "subject_id": subject_id,
                    "dx_group": dx_group,
                    "filename": filename,
                    "source_url": url,
                    "local_path": str(local_path),
                }
            )

    atlas = datasets.fetch_atlas_msdl(data_dir=str(cache_dir / "atlases"))
    masker = NiftiMapsMasker(
        maps_img=atlas.maps,
        standardize="zscore_sample",
        detrend=True,
        memory=str(cache_dir / "nilearn_cache"),
        memory_level=1,
    )

    subject_connectivities: list[np.ndarray] = []
    subject_edge_means: dict[str, float] = {}
    region_count: int | None = None

    for record in selected_records:
        time_series = masker.fit_transform(record["local_path"])
        if time_series.ndim != 2 or time_series.shape[0] < 20:
            continue

        corr = np.corrcoef(time_series.T)
        np.fill_diagonal(corr, 1.0)
        subject_connectivities.append(corr)

        if region_count is None:
            region_count = int(corr.shape[0])

        upper = corr[np.triu_indices_from(corr, k=1)]
        subject_edge_means[record["subject_id"]] = float(np.mean(upper))

    if len(subject_connectivities) < 2:
        raise RuntimeError("insufficient_subject_connectivities")

    mean_connectivity = np.mean(np.stack(subject_connectivities, axis=0), axis=0)
    mean_connectivity = (mean_connectivity + mean_connectivity.T) / 2.0
    np.fill_diagonal(mean_connectivity, 1.0)
    np.save(output_dir / "connectivity_matrix.npy", mean_connectivity)

    rows: list[dict] = []
    for dx_group, label in [(0, "control"), (1, "adhd")]:
        ids = [r["subject_id"] for r in selected_records if r["dx_group"] == dx_group]
        ids = [sid for sid in ids if sid in subject_edge_means]
        if not ids:
            continue
        means = [subject_edge_means[sid] for sid in ids]
        rows.append(
            {
                "group_label": label,
                "dx_group": dx_group,
                "n_subjects": len(ids),
                "mean_edge_connectivity": float(np.mean(means)),
                "std_edge_connectivity": float(np.std(means, ddof=0)),
                "subject_ids": ";".join(sorted(ids)),
            }
        )

    if sorted([int(r["dx_group"]) for r in rows]) != [0, 1]:
        raise RuntimeError("computed_rows_missing_required_groups")

    write_group_csv(sorted(rows, key=lambda r: int(r["dx_group"])))

    row_counts = {str(int(r["dx_group"])): int(r["n_subjects"]) for r in rows}

    run_metadata = {
        "task_id": TASK_ID,
        "dataset_source": "OpenNeuro",
        "dataset_id": DATASET_ID,
        "status": "ok",
        "reason": "computed",
        "snapshot_tag": snapshot_tag,
        "participants_total": int(len(participants)),
        "used_subject_ids": sorted({r["subject_id"] for r in selected_records if r["subject_id"] in subject_edge_means}),
        "used_subject_count": int(len({r["subject_id"] for r in selected_records if r["subject_id"] in subject_edge_means})),
        "used_file_paths": [r["local_path"] for r in selected_records],
        "used_source_urls": [r["source_url"] for r in selected_records],
        "group_subject_counts": {
            "0": int(row_counts.get("0", 0)),
            "1": int(row_counts.get("1", 0)),
        },
        "n_regions": int(region_count or 0),
        "matrix_shape": [int(x) for x in mean_connectivity.shape],
        "matrix_upper_mean": float(np.mean(mean_connectivity[np.triu_indices_from(mean_connectivity, k=1)])),
    }
    write_metadata(run_metadata)

    print(f"Wrote outputs to {output_dir}")
    print(f"used_subjects={run_metadata['used_subject_count']} snapshot={snapshot_tag}")
except Exception as exc:
    reason = safe_reason(exc)
    write_failfast(reason)
    print(f"failed_precondition: {reason}")
