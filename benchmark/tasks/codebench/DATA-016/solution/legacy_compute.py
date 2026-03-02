import csv
import json
import os
import re
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np
from nilearn import datasets


TASK_ID = "DATA-016"
DATASET_SOURCE = "Nilearn"
DATASET_ID = "fetch_oasis_vbm"
N_SUBJECTS = int(os.environ.get("N_SUBJECTS", "40"))


def choose_cache_dir() -> Path:
    candidates = []
    env_cache = os.environ.get("TASK_CACHE_DIR")
    if env_cache:
        candidates.append(Path(env_cache))
    candidates.extend([Path("/task/cache"), Path("/app/cache"), Path(os.environ["OUTPUT_DIR"]) / ".cache"])

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return path
        except Exception:
            continue
    raise RuntimeError("no_writable_cache_dir")


def infer_subject_id(path: str) -> str:
    name = Path(path).name
    m = re.search(r"(OAS1_\d{4}_MR1)", name)
    if m:
        return m.group(1)
    m2 = re.search(r"(sub-[A-Za-z0-9][A-Za-z0-9_-]*)", path)
    if m2:
        return m2.group(1)
    return Path(path).stem


def safe_float(v) -> float:
    try:
        x = float(v)
        if np.isfinite(x):
            return x
    except Exception:
        pass
    return float("nan")


def summarize_image(path: str) -> dict:
    img = nib.load(path)
    arr = np.asanyarray(img.dataobj, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {
            "shape": tuple(arr.shape),
            "mean": float("nan"),
            "std": float("nan"),
            "nonzero_ratio": 0.0,
            "mask": np.zeros(arr.shape, dtype=bool),
        }

    mask = finite > 0.2
    return {
        "shape": tuple(arr.shape),
        "mean": float(np.mean(finite)),
        "std": float(np.std(finite)),
        "nonzero_ratio": float(np.count_nonzero(finite) / finite.size),
        "mask": mask.reshape(arr.shape),
    }


def dice(mask_a: np.ndarray, mask_b: np.ndarray) -> float:
    if mask_a.shape != mask_b.shape:
        return float("nan")
    a = np.count_nonzero(mask_a)
    b = np.count_nonzero(mask_b)
    if a + b == 0:
        return 0.0
    inter = np.count_nonzero(mask_a & mask_b)
    return float(2.0 * inter / (a + b))


def robust_limits(values: list[float], n_sigma: float = 3.0) -> tuple[float, float]:
    arr = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if arr.size < 2:
        return float("-inf"), float("inf")
    mu = float(np.mean(arr))
    sigma = float(np.std(arr))
    if sigma < 1e-8:
        return mu - 1e-8, mu + 1e-8
    return mu - n_sigma * sigma, mu + n_sigma * sigma


def iqr_lower_limit(values: list[float]) -> float:
    arr = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if arr.size < 4:
        return float("-inf")
    q1, q3 = np.percentile(arr, [25.0, 75.0])
    iqr = float(q3 - q1)
    return float(q1 - 1.5 * iqr)


def write_flagged_csv(path: Path, rows: list[dict]) -> None:
    columns = [
        "subject_id",
        "issue_code",
        "severity",
        "metric_name",
        "metric_value",
        "threshold",
        "details",
        "gm_path",
        "wm_path",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in columns})


def html_escape(v) -> str:
    return (
        str(v)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def write_html_report(path: Path, run_meta: dict, flags: list[dict], thresholds: dict) -> None:
    issue_counts = Counter(row["issue_code"] for row in flags)
    rows_html = []
    for row in flags[:300]:
        rows_html.append(
            "<tr>"
            f"<td>{html_escape(row.get('subject_id', ''))}</td>"
            f"<td>{html_escape(row.get('issue_code', ''))}</td>"
            f"<td>{html_escape(row.get('severity', ''))}</td>"
            f"<td>{html_escape(row.get('metric_name', ''))}</td>"
            f"<td>{html_escape(row.get('metric_value', ''))}</td>"
            f"<td>{html_escape(row.get('threshold', ''))}</td>"
            f"<td>{html_escape(row.get('details', ''))}</td>"
            "</tr>"
        )

    issue_items = "".join(
        f"<li><b>{html_escape(k)}</b>: {v}</li>" for k, v in sorted(issue_counts.items())
    ) or "<li>No flagged rows</li>"

    threshold_items = "".join(
        f"<li><b>{html_escape(k)}</b>: {html_escape(v)}</li>" for k, v in sorted(thresholds.items())
    )

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>OASIS VBM QA Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; color: #222; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; font-size: 12px; text-align: left; }}
    th {{ background: #f3f3f3; }}
    code {{ background: #f7f7f7; padding: 1px 4px; }}
  </style>
</head>
<body>
  <h1>OASIS VBM QA Report</h1>
  <p><b>Status:</b> {html_escape(run_meta.get("status", ""))}</p>
  <p><b>Reason:</b> {html_escape(run_meta.get("reason", ""))}</p>
  <p><b>Dataset:</b> <code>{html_escape(run_meta.get("dataset_id", ""))}</code></p>
  <p><b>Total subjects analyzed:</b> {run_meta.get("n_subjects_total", 0)}</p>
  <p><b>Flagged rows:</b> {run_meta.get("n_flagged_rows", 0)}</p>
  <p><b>Unique flagged subjects:</b> {run_meta.get("n_unique_flagged_subjects", 0)}</p>
  <h2>Thresholds</h2>
  <ul>{threshold_items}</ul>
  <h2>Issue Counts</h2>
  <ul>{issue_items}</ul>
  <h2>Flagged Rows (first 300)</h2>
  <table>
    <thead>
      <tr>
        <th>subject_id</th>
        <th>issue_code</th>
        <th>severity</th>
        <th>metric_name</th>
        <th>metric_value</th>
        <th>threshold</th>
        <th>details</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</body>
</html>"""
    path.write_text(html_text, encoding="utf-8")


def main() -> None:
    output_dir = Path(os.environ.get("OUTPUT_DIR", "/app/output")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    flags: list[dict] = []
    thresholds = {
        "nonzero_ratio_min": 0.10,
        "intensity_n_sigma": 3.0,
        "registration_dice_rule": "lower_iqr_fence",
    }
    run_meta = {
        "task_id": TASK_ID,
        "dataset_source": DATASET_SOURCE,
        "dataset_id": DATASET_ID,
        "status": "failed_precondition",
        "reason": "not_started",
        "cache_dir": "",
        "n_subjects_total": 0,
        "n_subjects_with_gm": 0,
        "n_subjects_with_wm": 0,
        "n_flagged_rows": 0,
        "n_unique_flagged_subjects": 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "used_subject_ids": [],
        "thresholds": thresholds,
    }

    try:
        cache_dir = choose_cache_dir()
        run_meta["cache_dir"] = str(cache_dir)

        dataset = datasets.fetch_oasis_vbm(
            n_subjects=N_SUBJECTS,
            data_dir=str(cache_dir),
            resume=True,
            verbose=0,
        )

        gm_by_subject = {}
        wm_by_subject = {}
        for path in dataset.gray_matter_maps:
            gm_by_subject[infer_subject_id(path)] = str(path)
        for path in dataset.white_matter_maps:
            wm_by_subject[infer_subject_id(path)] = str(path)

        ext = dataset.ext_vars.copy()
        ext["id"] = ext["id"].astype(str)
        ext_by_subject = {row["id"]: row for _, row in ext.iterrows()}

        subjects = sorted(set(gm_by_subject) | set(wm_by_subject) | set(ext_by_subject))
        if not subjects:
            raise RuntimeError("no_subjects_resolved")

        records = []
        for sid in subjects:
            gm_path = gm_by_subject.get(sid, "")
            wm_path = wm_by_subject.get(sid, "")
            age = safe_float(ext_by_subject[sid]["age"]) if sid in ext_by_subject else float("nan")
            sex = str(ext_by_subject[sid]["mf"]) if sid in ext_by_subject else ""

            rec = {
                "subject_id": sid,
                "age": age,
                "sex": sex,
                "gm_path": gm_path,
                "wm_path": wm_path,
                "gm_stats": None,
                "wm_stats": None,
                "dice_overlap": float("nan"),
            }

            if not gm_path or not Path(gm_path).exists():
                flags.append(
                    {
                        "subject_id": sid,
                        "issue_code": "missing_modality",
                        "severity": "error",
                        "metric_name": "gray_matter_maps",
                        "metric_value": 0,
                        "threshold": "must_exist",
                        "details": "Gray matter map missing",
                        "gm_path": gm_path,
                        "wm_path": wm_path,
                    }
                )
            else:
                rec["gm_stats"] = summarize_image(gm_path)

            if not wm_path or not Path(wm_path).exists():
                flags.append(
                    {
                        "subject_id": sid,
                        "issue_code": "missing_modality",
                        "severity": "error",
                        "metric_name": "white_matter_maps",
                        "metric_value": 0,
                        "threshold": "must_exist",
                        "details": "White matter map missing",
                        "gm_path": gm_path,
                        "wm_path": wm_path,
                    }
                )
            else:
                rec["wm_stats"] = summarize_image(wm_path)

            if rec["gm_stats"] and rec["wm_stats"]:
                rec["dice_overlap"] = dice(rec["gm_stats"]["mask"], rec["wm_stats"]["mask"])
            records.append(rec)

        gm_shapes = [r["gm_stats"]["shape"] for r in records if r["gm_stats"]]
        wm_shapes = [r["wm_stats"]["shape"] for r in records if r["wm_stats"]]
        gm_modal_shape = Counter(gm_shapes).most_common(1)[0][0] if gm_shapes else None
        wm_modal_shape = Counter(wm_shapes).most_common(1)[0][0] if wm_shapes else None

        gm_means = [r["gm_stats"]["mean"] for r in records if r["gm_stats"]]
        wm_means = [r["wm_stats"]["mean"] for r in records if r["wm_stats"]]
        dice_values = [r["dice_overlap"] for r in records if np.isfinite(r["dice_overlap"])]

        gm_lo, gm_hi = robust_limits(gm_means, thresholds["intensity_n_sigma"])
        wm_lo, wm_hi = robust_limits(wm_means, thresholds["intensity_n_sigma"])
        dice_lo = iqr_lower_limit(dice_values)

        thresholds["gm_mean_limits"] = [gm_lo, gm_hi]
        thresholds["wm_mean_limits"] = [wm_lo, wm_hi]
        thresholds["dice_lower_limit"] = dice_lo
        thresholds["gm_modal_shape"] = list(gm_modal_shape) if gm_modal_shape else []
        thresholds["wm_modal_shape"] = list(wm_modal_shape) if wm_modal_shape else []

        for rec in records:
            sid = rec["subject_id"]
            gm_path = rec["gm_path"]
            wm_path = rec["wm_path"]

            if rec["gm_stats"]:
                if rec["gm_stats"]["nonzero_ratio"] < thresholds["nonzero_ratio_min"]:
                    flags.append(
                        {
                            "subject_id": sid,
                            "issue_code": "low_signal",
                            "severity": "warn",
                            "metric_name": "gm_nonzero_ratio",
                            "metric_value": rec["gm_stats"]["nonzero_ratio"],
                            "threshold": f">={thresholds['nonzero_ratio_min']}",
                            "details": "Low non-zero voxel ratio in GM map",
                            "gm_path": gm_path,
                            "wm_path": wm_path,
                        }
                    )
                if rec["gm_stats"]["mean"] < gm_lo or rec["gm_stats"]["mean"] > gm_hi:
                    flags.append(
                        {
                            "subject_id": sid,
                            "issue_code": "intensity_outlier",
                            "severity": "warn",
                            "metric_name": "gm_mean",
                            "metric_value": rec["gm_stats"]["mean"],
                            "threshold": f"[{gm_lo:.6f}, {gm_hi:.6f}]",
                            "details": "GM mean intensity outside cohort limits",
                            "gm_path": gm_path,
                            "wm_path": wm_path,
                        }
                    )
                if gm_modal_shape and rec["gm_stats"]["shape"] != gm_modal_shape:
                    flags.append(
                        {
                            "subject_id": sid,
                            "issue_code": "shape_mismatch",
                            "severity": "error",
                            "metric_name": "gm_shape",
                            "metric_value": str(rec["gm_stats"]["shape"]),
                            "threshold": str(gm_modal_shape),
                            "details": "GM image shape differs from modal cohort shape",
                            "gm_path": gm_path,
                            "wm_path": wm_path,
                        }
                    )

            if rec["wm_stats"]:
                if rec["wm_stats"]["nonzero_ratio"] < thresholds["nonzero_ratio_min"]:
                    flags.append(
                        {
                            "subject_id": sid,
                            "issue_code": "low_signal",
                            "severity": "warn",
                            "metric_name": "wm_nonzero_ratio",
                            "metric_value": rec["wm_stats"]["nonzero_ratio"],
                            "threshold": f">={thresholds['nonzero_ratio_min']}",
                            "details": "Low non-zero voxel ratio in WM map",
                            "gm_path": gm_path,
                            "wm_path": wm_path,
                        }
                    )
                if rec["wm_stats"]["mean"] < wm_lo or rec["wm_stats"]["mean"] > wm_hi:
                    flags.append(
                        {
                            "subject_id": sid,
                            "issue_code": "intensity_outlier",
                            "severity": "warn",
                            "metric_name": "wm_mean",
                            "metric_value": rec["wm_stats"]["mean"],
                            "threshold": f"[{wm_lo:.6f}, {wm_hi:.6f}]",
                            "details": "WM mean intensity outside cohort limits",
                            "gm_path": gm_path,
                            "wm_path": wm_path,
                        }
                    )
                if wm_modal_shape and rec["wm_stats"]["shape"] != wm_modal_shape:
                    flags.append(
                        {
                            "subject_id": sid,
                            "issue_code": "shape_mismatch",
                            "severity": "error",
                            "metric_name": "wm_shape",
                            "metric_value": str(rec["wm_stats"]["shape"]),
                            "threshold": str(wm_modal_shape),
                            "details": "WM image shape differs from modal cohort shape",
                            "gm_path": gm_path,
                            "wm_path": wm_path,
                        }
                    )

            if np.isfinite(rec["dice_overlap"]) and rec["dice_overlap"] < dice_lo:
                flags.append(
                    {
                        "subject_id": sid,
                        "issue_code": "registration_outlier",
                        "severity": "warn",
                        "metric_name": "gm_wm_dice",
                        "metric_value": rec["dice_overlap"],
                        "threshold": f">={dice_lo:.6f}",
                        "details": "GM/WM overlap below cohort lower fence",
                        "gm_path": gm_path,
                        "wm_path": wm_path,
                    }
                )

        run_meta["status"] = "ok"
        run_meta["reason"] = "qa_computed_from_oasis_vbm"
        run_meta["n_subjects_total"] = len(subjects)
        run_meta["n_subjects_with_gm"] = sum(1 for r in records if r["gm_stats"] is not None)
        run_meta["n_subjects_with_wm"] = sum(1 for r in records if r["wm_stats"] is not None)
        run_meta["n_flagged_rows"] = len(flags)
        run_meta["n_unique_flagged_subjects"] = len({row["subject_id"] for row in flags})
        run_meta["used_subject_ids"] = subjects

    except Exception as exc:
        run_meta["status"] = "failed_precondition"
        run_meta["reason"] = f"{type(exc).__name__}:{exc}"
        run_meta["traceback_tail"] = traceback.format_exc(limit=1)
        flags = [
            {
                "subject_id": "N/A",
                "issue_code": "precondition_failure",
                "severity": "error",
                "metric_name": "dataset_fetch",
                "metric_value": 0,
                "threshold": "must_resolve",
                "details": run_meta["reason"],
                "gm_path": "",
                "wm_path": "",
            }
        ]
        run_meta["n_flagged_rows"] = 1
        run_meta["n_unique_flagged_subjects"] = 0

    write_flagged_csv(output_dir / "flagged_subjects.csv", flags)
    write_html_report(output_dir / "qa_report.html", run_meta, flags, thresholds)
    (output_dir / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")
    print(f"status={run_meta['status']} reason={run_meta['reason']} flagged={run_meta['n_flagged_rows']}")


if __name__ == "__main__":
    main()
