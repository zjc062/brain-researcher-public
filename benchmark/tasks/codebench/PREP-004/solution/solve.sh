#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/prep_004"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/prep_004"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "PREP-004" \
  --dataset-source "OpenNeuro" \
  --dataset-id "ds003592" \
  --required-outputs-json '["motion_corrected_bold.nii.gz", "motion_parameters.txt", "run_metadata.json"]' \
  --output-schema-json '{"motion_corrected_bold.nii.gz": {"type": "nifti"}, "motion_parameters.txt": {"type": "text"}, "run_metadata.json": {"type": "json"}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
