#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/conn_002"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/conn_002"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "CONN-002" \
  --dataset-source "Nilearn" \
  --dataset-id "fetch_surf_nki_enhanced" \
  --required-outputs-json '["network_timeseries.csv", "correlation_matrix.png"]' \
  --output-schema-json '{"network_timeseries.csv": {"type": "csv", "required_columns": ["subject_id", "timepoint", "network_id", "network_label", "signal"]}, "correlation_matrix.png": {"type": "png", "min_size_px": [200, 200]}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
