#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/seg_002"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/seg_002"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py"   --task-id "SEG-002"   --dataset-source "OpenNeuro"   --dataset-id "ds002424"   --required-outputs-json '["c1_gm.nii.gz", "c2_wm.nii.gz", "c3_csf.nii.gz", "input_manifest.csv", "run_metadata.json"]'   --output-schema-json '{"c1_gm.nii.gz": {"type": "nifti"}, "c2_wm.nii.gz": {"type": "nifti"}, "c3_csf.nii.gz": {"type": "nifti"}, "input_manifest.csv": {"type": "csv", "required_columns": ["dataset_id", "source_path", "bytes", "sha256"]}, "run_metadata.json": {"type": "json", "required_keys": ["task_id", "dataset_source", "dataset_id", "status", "reason", "method", "n_input_files", "n_subjects", "records_count", "bytes_total", "hash_manifest_sha256"]}}'   --output-dir "$OUTPUT_DIR"   --cache-dir "$CACHE_DIR"
