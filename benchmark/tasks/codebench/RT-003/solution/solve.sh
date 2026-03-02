#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/rt_003"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/rt_003"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py"   --task-id "RT-003"   --dataset-source "Provided"   --dataset-id "streaming_fmri_volumes"   --required-outputs-json '["motion_params.csv", "qa_flags.json", "input_manifest.csv", "run_metadata.json"]'   --output-schema-json '{"motion_params.csv": {"type": "csv", "required_columns": ["record_id", "task_id", "dataset_id", "source_path", "metric_name", "metric_value", "status", "reason"]}, "qa_flags.json": {"type": "json", "required_keys": ["task_id", "dataset_source", "dataset_id", "status", "reason", "method", "records_count"]}, "input_manifest.csv": {"type": "csv", "required_columns": ["dataset_id", "source_path", "bytes", "sha256"]}, "run_metadata.json": {"type": "json", "required_keys": ["task_id", "dataset_source", "dataset_id", "status", "reason", "method", "n_input_files", "n_subjects", "records_count", "bytes_total", "hash_manifest_sha256"]}}'   --output-dir "$OUTPUT_DIR"   --cache-dir "$CACHE_DIR"
