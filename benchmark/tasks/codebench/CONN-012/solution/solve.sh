#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/conn_012"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/conn_012"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "CONN-012" \
  --dataset-source "Nilearn" \
  --dataset-id "fetch_abide_pcp" \
  --required-outputs-json '["significant_edges.csv", "edge_statistics.npy"]' \
  --output-schema-json '{"significant_edges.csv": {"type": "csv", "required_columns": ["edge_i", "edge_j", "t_stat", "p_value", "mean_asd", "mean_control", "effect_size", "significant"]}, "edge_statistics.npy": {"type": "file"}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
