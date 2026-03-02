Task: Anatomical QC on ds002424 (real T1w-derived metrics) (OPENNEURO-QC-003)

Scope
- Category: Quality Control (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds002424
- Strict mode: real anatomical NIfTI inputs + hash traceability.

Goal
- Discover real subject/session anatomical T1w files from OpenNeuro snapshot metadata.
- Compute deterministic QC metrics from real voxel intensities (`snr`, `cnr`, `qi1`).
- Emit subject-level QC table, input manifest with hashes, and consistent run metadata.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `anatomical_qc.csv`
   - required columns: `subject_id`, `snr`, `cnr`, `qi1`, `overall_rating`, `status`, `reason`, `dataset_id`, `snapshot_tag`, `method`
2. `input_manifest.csv`
   - required columns: `dataset_id`, `snapshot_tag`, `subject_id`, `session`, `anat_relpath`, `local_path`, `bytes`, `sha256`
3. `run_metadata.json`
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `processing_subject_count`, `processing_run_count`, `input_file_count`, `hash_manifest_sha256`

Hard Requirements
- No placeholder or random fabricated outputs.
- QC metrics must be computed from real downloaded anatomical images.
- Manifest hashes must trace consumed input files.
- `run_metadata.json` must be cross-consistent with CSV and manifest.

Fail-fast
- If no usable anatomical data can be resolved, emit structured `failed_precondition` outputs (not fake metrics).
