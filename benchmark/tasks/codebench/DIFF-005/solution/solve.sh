#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/diff_005"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/diff_005"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "DIFF-005" \
  --dataset-source "Provided" \
  --dataset-id "custom_dwi_aal_atlas" \
  --required-outputs-json '["structural_connectome.csv", "connectome_plot.png"]' \
  --output-schema-json '{"structural_connectome.csv": {"type": "csv", "required_columns": ["region_i", "region_j", "index_i", "index_j", "weight", "mean_fa_i", "mean_fa_j", "n_voxels_i", "n_voxels_j"]}, "connectome_plot.png": {"type": "png", "min_size_px": [300, 300]}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
