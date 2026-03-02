#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/data_017"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/data_017"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "DATA-017" \
  --dataset-source "Provided" \
  --dataset-id "custom_missing_modalities" \
  --required-outputs-json '["preflight_check.json", "fail_fast_reason.txt"]' \
  --output-schema-json '{"preflight_check.json": {"type": "json", "required_keys": ["status", "required_inputs", "missing_inputs", "checked_paths"]}, "fail_fast_reason.txt": {"type": "text"}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
