#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/data_016"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/data_016"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "DATA-016" \
  --dataset-source "Nilearn" \
  --dataset-id "fetch_oasis_vbm" \
  --required-outputs-json '["qa_report.html", "flagged_subjects.csv"]' \
  --output-schema-json '{"qa_report.html": {"type": "html"}, "flagged_subjects.csv": {"type": "csv", "required_columns": ["subject_id", "issue_code", "severity", "metric_name", "metric_value", "threshold", "details", "gm_path", "wm_path"]}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
