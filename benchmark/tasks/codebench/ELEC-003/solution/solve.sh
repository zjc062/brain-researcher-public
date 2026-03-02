#!/bin/bash

set -euo pipefail

OUTPUT_DIR="${OUTPUT_DIR:-/app/output}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_CACHE="/task/cache/elec_003"
if [ -z "${CACHE_DIR:-}" ]; then
  if mkdir -p "${DEFAULT_CACHE}" 2>/dev/null; then
    CACHE_DIR="${DEFAULT_CACHE}"
  else
    CACHE_DIR="${OUTPUT_DIR}/_cache/elec_003"
  fi
fi
mkdir -p "${OUTPUT_DIR}" "${CACHE_DIR}"
export OUTPUT_DIR TASK_DIR CACHE_DIR

python3 "$TASK_DIR/../_shared/task_native_runner.py" \
  --task-id "ELEC-003" \
  --dataset-source "Provided" \
  --dataset-id "mne_sample_dataset" \
  --required-outputs-json '["auditory_evoked.fif", "visual_evoked.fif", "evoked_plot.png"]' \
  --output-schema-json '{"auditory_evoked.fif": {"type": "file"}, "visual_evoked.fif": {"type": "file"}, "evoked_plot.png": {"type": "png", "min_size_px": [300, 300]}}' \
  --output-dir "$OUTPUT_DIR" \
  --cache-dir "$CACHE_DIR"
