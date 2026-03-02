#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/clin_005"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/clin_005"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "CLIN-005" \
  --dataset-source "Nilearn" \
  --dataset-id "fetch_oasis_vbm" \
  --required-outputs-json '["predicted_ages.csv", "age_gap_distribution.png"]' \
  --output-schema-json '{"predicted_ages.csv": {"type": "csv", "required_columns": ["subject_id", "chronological_age", "predicted_age", "brain_age_gap", "split"]}, "age_gap_distribution.png": {"type": "png", "min_size_px": [200, 200]}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
