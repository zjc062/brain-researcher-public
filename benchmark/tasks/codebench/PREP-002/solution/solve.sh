#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/prep_002"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/prep_002"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/solution/legacy_compute.py"
