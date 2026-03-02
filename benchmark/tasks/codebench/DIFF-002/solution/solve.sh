#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/diff_002"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/diff_002"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "DIFF-002" \
  --dataset-source "Provided" \
  --dataset-id "custom_dwi_data" \
  --required-outputs-json '["dti_FA.nii.gz", "dti_MD.nii.gz", "dti_tensors.nii.gz"]' \
  --output-schema-json '{"dti_FA.nii.gz": {"type": "nifti", "no_nan": true}, "dti_MD.nii.gz": {"type": "nifti", "no_nan": true}, "dti_tensors.nii.gz": {"type": "nifti", "no_nan": true}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
