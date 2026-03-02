#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/reg_002"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/reg_002"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "REG-002" \
  --dataset-source "OpenNeuro" \
  --dataset-id "ds002424" \
  --required-outputs-json '["flirt_matrix.mat", "coregistered_bold.nii.gz", "run_metadata.json"]' \
  --output-schema-json '{"flirt_matrix.mat": {"type": "file"}, "coregistered_bold.nii.gz": {"type": "nifti"}, "run_metadata.json": {"type": "json"}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
