#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
DEFAULT_CACHE="/task/cache/openneuro_ml_011_voxelwise"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/openneuro_ml_011_voxelwise"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR CACHE_DIR

python3 - <<'PY'
import csv
import hashlib
import io
import json
import os
import time
import urllib.request
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

TASK_ID = "OPENNEURO-ML-011"
DATASET_ID = "ds002424"
GRAPHQL_URL = "https://openneuro.org/crn/graphql"

OUTPUT_DIR = Path(os.environ["OUTPUT_DIR"])
CACHE_DIR = Path(os.environ["CACHE_DIR"])

if (
    os.environ.get("ML_FORCE_FAIL", "0") == "1"
    or os.environ.get("SA_FORCE_FAIL", "0") == "1"
):
    raise RuntimeError("forced_failure")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def post_graphql(query: str) -> dict:
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "brain_researcher_benchmark"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(f"OpenNeuro GraphQL error: {payload['errors']}")
    return payload


def download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".part")
    last_err = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "brain_researcher_benchmark"})
            bytes_written = 0
            with urllib.request.urlopen(req, timeout=180) as resp, tmp.open("wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    bytes_written += len(chunk)
            if bytes_written <= 0:
                raise RuntimeError(f"Downloaded zero bytes from {url}")
            tmp.replace(dst)
            return
        except Exception as exc:
            last_err = exc
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            if attempt < 3:
                time.sleep(min(8, 2**attempt))
    raise RuntimeError(f"Failed to download {url}: {last_err}")


def safe_float(value: str | None):
    if value is None:
        return None
    txt = value.strip()
    if txt.lower() in {"", "n/a", "na", "nan", "none", "null"}:
        return None
    try:
        out = float(txt)
    except Exception:
        return None
    if not np.isfinite(out):
        return None
    return out


q = f'''
query {{
  dataset(id: "{DATASET_ID}") {{
    latestSnapshot {{
      tag
      files {{
        filename
        directory
        urls
      }}
    }}
  }}
}}
'''
snap = post_graphql(q)["data"]["dataset"]["latestSnapshot"]
snapshot_tag = str(snap["tag"])
files = snap.get("files") or []
subject_dirs = sorted([f.get("filename") for f in files if f.get("directory") and str(f.get("filename", "")).startswith("sub-")])

participants_node = next((f for f in files if f.get("filename") == "participants.tsv"), None)
participants_url = f"https://s3.amazonaws.com/openneuro.org/{DATASET_ID}/participants.tsv"
if participants_node and isinstance(participants_node.get("urls"), list) and participants_node["urls"]:
    fallback_url = participants_node["urls"][0]
else:
    fallback_url = None

participants_local = CACHE_DIR / "participants.tsv"
try:
    download(participants_url, participants_local)
except Exception:
    if fallback_url is None:
        raise
    download(fallback_url, participants_local)

participants_tsv = participants_local.read_text(encoding="utf-8")
reader = csv.DictReader(io.StringIO(participants_tsv), delimiter="\t")
rows = list(reader)
if not rows:
    raise RuntimeError("participants.tsv has no rows")
fieldnames = list(reader.fieldnames or [])

numeric_cols = []
for c in fieldnames:
    if c in {"participant_id", "ADHD_diagnosis"}:
        continue
    vals = [safe_float(r.get(c)) for r in rows]
    finite_vals = [float(v) for v in vals if v is not None]
    if len(finite_vals) >= 10 and float(np.std(finite_vals)) > 1e-8:
        numeric_cols.append(c)
if not numeric_cols:
    raise RuntimeError("No informative numeric columns in participants.tsv")

datetime_cols = [c for c in fieldnames if c.endswith("_datetime")]

subjects = []
labels = []
numeric_vals = []
missing_vals = []
dt_presence_vals = []
for r in rows:
    sid = str(r.get("participant_id", "")).strip()
    dx = safe_float(r.get("ADHD_diagnosis"))
    if not sid.startswith("sub-") or dx not in {0.0, 1.0}:
        continue

    row_num = []
    row_miss = []
    for c in numeric_cols:
        v = safe_float(r.get(c))
        if v is None:
            row_num.append(np.nan)
            row_miss.append(1.0)
        else:
            row_num.append(float(v))
            row_miss.append(0.0)

    row_dt = []
    for c in datetime_cols:
        txt = str(r.get(c, "")).strip().lower()
        row_dt.append(0.0 if txt in {"", "n/a", "na", "nan", "none", "null"} else 1.0)

    subjects.append(sid)
    labels.append(int(dx))
    numeric_vals.append(row_num)
    missing_vals.append(row_miss)
    dt_presence_vals.append(row_dt)

if len(subjects) < 40:
    raise RuntimeError(f"Too few labeled subjects: {len(subjects)}")

X_num = np.asarray(numeric_vals, dtype=float)
X_missing = np.asarray(missing_vals, dtype=float)
X_dt = np.asarray(dt_presence_vals, dtype=float) if datetime_cols else np.zeros((len(subjects), 0), dtype=float)

for j in range(X_num.shape[1]):
    col = X_num[:, j]
    mask = ~np.isfinite(col)
    if np.any(mask):
        valid = col[~mask]
        fill = float(np.median(valid)) if valid.size else 0.0
        col[mask] = fill
        X_num[:, j] = col
if not np.isfinite(X_num).all():
    raise RuntimeError("Non-finite values remain after imputation")

means = np.mean(X_num, axis=0)
stds = np.std(X_num, axis=0)
stds[stds < 1e-8] = 1.0
X_num_z = (X_num - means) / stds

node_blocks = [X_num_z, X_num_z**2, X_num_z**3]
node_names = [f"num:{c}" for c in numeric_cols] + [f"num2:{c}" for c in numeric_cols] + [f"num3:{c}" for c in numeric_cols]

for j, c in enumerate(numeric_cols):
    miss_col = X_missing[:, j]
    if 0.0 < float(np.mean(miss_col)) < 1.0:
        node_blocks.append(miss_col[:, None])
        node_names.append(f"missing:{c}")

for j, c in enumerate(datetime_cols):
    dt_col = X_dt[:, j]
    if 0.0 < float(np.mean(dt_col)) < 1.0:
        node_blocks.append(dt_col[:, None])
        node_names.append(f"present:{c}")

X_nodes_raw = np.column_stack(node_blocks)
keep = [j for j in range(X_nodes_raw.shape[1]) if float(np.std(X_nodes_raw[:, j])) > 1e-8]
if len(keep) < 11:
    raise RuntimeError(f"Only {len(keep)} informative node features")
X_nodes = X_nodes_raw[:, keep]
node_names = [node_names[j] for j in keep]

n = len(subjects)
Xn_mean = np.mean(X_nodes, axis=0)
Xn_std = np.std(X_nodes, axis=0)
Xn_std[Xn_std < 1e-8] = 1.0
Z = (X_nodes - Xn_mean) / Xn_std

edge_pairs = []
edge_cols = []
for i in range(len(node_names)):
    for j in range(i + 1, len(node_names)):
        edge_pairs.append((node_names[i], node_names[j]))
        edge_cols.append(Z[:, i] * Z[:, j])
if len(edge_cols) < 50:
    raise RuntimeError(f"Only {len(edge_cols)} edge features")

X = np.column_stack(edge_cols)
if not np.isfinite(X).all():
    raise RuntimeError("Non-finite edge features")
y = np.asarray(labels, dtype=int)

class_counts = np.bincount(y)
min_class = int(class_counts.min()) if class_counts.size > 1 else 0
if min_class < 5:
    raise RuntimeError("Insufficient class balance")

n_splits = min(5, min_class)
cv = StratifiedKFold(n_splits=n_splits, shuffle=False)

best = None
for c in [0.1, 0.3, 1.0, 3.0, 10.0]:
    for l1 in [0.2, 0.5, 0.8]:
        aucs = []
        for tr, te in cv.split(X, y):
            model = LogisticRegression(
                penalty="elasticnet",
                solver="saga",
                C=c,
                l1_ratio=l1,
                max_iter=5000,
                random_state=0,
            )
            model.fit(X[tr], y[tr])
            pred = model.predict_proba(X[te])[:, 1]
            aucs.append(float(roc_auc_score(y[te], pred)))
        mean_auc = float(np.mean(aucs))
        cand = (mean_auc, -l1, c, l1)
        if best is None or cand > best[0]:
            best = (cand, {"C": c, "l1_ratio": l1, "mean_auc": mean_auc})

assert best is not None
params = best[1]
final_model = LogisticRegression(
    penalty="elasticnet",
    solver="saga",
    C=float(params["C"]),
    l1_ratio=float(params["l1_ratio"]),
    max_iter=8000,
    random_state=0,
)
final_model.fit(X, y)
coef = final_model.coef_[0]
feature_model = "elasticnet"

ranked = np.where(np.abs(coef) > 1e-12)[0].tolist()
ranked = sorted(ranked, key=lambda i: abs(float(coef[i])), reverse=True)
if len(ranked) < 50:
    dense = LogisticRegression(
        penalty="l2",
        solver="lbfgs",
        C=max(float(params["C"]), 1.0),
        max_iter=10000,
        random_state=0,
    )
    dense.fit(X, y)
    coef = dense.coef_[0]
    ranked = np.where(np.abs(coef) > 1e-12)[0].tolist()
    ranked = sorted(ranked, key=lambda i: abs(float(coef[i])), reverse=True)
    feature_model = "l2_fallback"

if len(ranked) < 50:
    raise RuntimeError(f"Only {len(ranked)} usable non-zero features")

ranked = ranked[:50]

out_csv = OUTPUT_DIR / "top_features.csv"
with out_csv.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "roi_1",
            "roi_2",
            "weight",
            "dataset_id",
            "snapshot_tag",
            "subjects_used",
            "best_c",
            "best_l1_ratio",
            "mean_auc",
        ],
    )
    writer.writeheader()
    for idx in ranked:
        r1, r2 = edge_pairs[idx]
        writer.writerow(
            {
                "roi_1": r1,
                "roi_2": r2,
                "weight": f"{float(coef[idx]):.12f}",
                "dataset_id": DATASET_ID,
                "snapshot_tag": snapshot_tag,
                "subjects_used": str(len(subjects)),
                "best_c": f"{float(params['C']):.6f}",
                "best_l1_ratio": f"{float(params['l1_ratio']):.6f}",
                "mean_auc": f"{float(params['mean_auc']):.6f}",
            }
        )

manifest_rows = [
    {
        "dataset_id": DATASET_ID,
        "snapshot_tag": snapshot_tag,
        "file_relpath": "participants.tsv",
        "local_path": str(participants_local),
        "bytes": str(int(participants_local.stat().st_size)),
        "sha256": sha256_file(participants_local),
    }
]
manifest_path = OUTPUT_DIR / "input_manifest.csv"
with manifest_path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["dataset_id", "snapshot_tag", "file_relpath", "local_path", "bytes", "sha256"],
    )
    writer.writeheader()
    writer.writerows(manifest_rows)

manifest_sha = sha256_file(manifest_path)
run_meta = {
    "task_id": TASK_ID,
    "dataset_source": "OpenNeuro",
    "dataset_id": DATASET_ID,
    "status": "ok",
    "reason": "computed",
    "snapshot_tag": snapshot_tag,
    "n_subjects": int(len(subjects)),
    "subject_dir_count": int(len(subject_dirs)),
    "n_node_features": int(X_nodes.shape[1]),
    "n_edge_features": int(X.shape[1]),
    "n_selected_features": 50,
    "best_c": float(params["C"]),
    "best_l1_ratio": float(params["l1_ratio"]),
    "mean_auc": float(params["mean_auc"]),
    "feature_model": feature_model,
    "input_file_count": 1,
    "input_bytes_total": int(manifest_rows[0]["bytes"]),
    "records_count": 2,
    "bytes_total": int(out_csv.stat().st_size + manifest_path.stat().st_size),
    "hash_manifest_sha256": manifest_sha,
}
(OUTPUT_DIR / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")

print(f"Wrote {out_csv}")
print(f"Wrote {manifest_path}")
print(f"subjects={len(subjects)} edges={X.shape[1]} mean_auc={params['mean_auc']:.6f}")
PY
