#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/conn_001"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/conn_001"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "CONN-001" \
  --dataset-source "OpenNeuro" \
  --dataset-id "ds002424" \
  --required-outputs-json '["connectivity_matrix.npy", "group_comparison.csv"]' \
  --output-schema-json '{"connectivity_matrix.npy": {"type": "file"}, "group_comparison.csv": {"type": "csv", "required_columns": ["group_label", "dx_group", "n_subjects", "mean_edge_connectivity", "std_edge_connectivity", "subject_ids"]}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
