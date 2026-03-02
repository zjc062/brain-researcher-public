#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/prep_012"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/prep_012"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "PREP-012" \
  --dataset-source "OpenNeuro" \
  --dataset-id "ds000105" \
  --required-outputs-json '["cleaned_bold.nii.gz", "compcor_components.tsv", "run_metadata.json"]' \
  --output-schema-json '{"cleaned_bold.nii.gz": {"type": "nifti"}, "compcor_components.tsv": {"type": "tsv"}, "run_metadata.json": {"type": "json"}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
