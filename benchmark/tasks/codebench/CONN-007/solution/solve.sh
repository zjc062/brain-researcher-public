#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/conn_007"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/conn_007"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "CONN-007" \
  --dataset-source "Nilearn" \
  --dataset-id "fetch_abide_pcp" \
  --required-outputs-json '["graph_metrics.csv", "small_world_sigma.txt"]' \
  --output-schema-json '{"graph_metrics.csv": {"type": "csv", "required_columns": ["subject_id", "dx_group", "mean_degree", "density", "clustering_coeff", "path_length"]}, "small_world_sigma.txt": {"type": "text"}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
