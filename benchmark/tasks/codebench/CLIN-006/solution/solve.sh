#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/clin_006"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/clin_006"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "CLIN-006" \
  --dataset-source "Provided" \
  --dataset-id "simulated_lesion_symptom_data" \
  --required-outputs-json '["vlsm_map.nii.gz", "deficit_correlations.csv"]' \
  --output-schema-json '{"vlsm_map.nii.gz": {"type": "nifti", "no_nan": true}, "deficit_correlations.csv": {"type": "csv", "required_columns": ["voxel_index", "x", "y", "z", "correlation_r", "t_stat", "p_value", "n_subjects", "status", "reason"]}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
