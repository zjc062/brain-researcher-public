#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/clin_014"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/clin_014"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "CLIN-014" \
  --dataset-source "Provided" \
  --dataset-id "simulated_treatment_dataset" \
  --required-outputs-json '["responder_model.pkl", "predictive_map.nii.gz"]' \
  --output-schema-json '{"responder_model.pkl": {"type": "pickle"}, "predictive_map.nii.gz": {"type": "nifti", "no_nan": true}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
