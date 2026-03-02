Task: Age prediction with uncertainty output (real BOLD-derived features) (OPENNEURO-ML-012)

Scope
- Category: Machine Learning (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds000030
- Strict mode: real participant age metadata + real BOLD-derived features.

Goal
- Resolve real ds000030 subjects with age labels and BOLD runs.
- Build subject-level imaging features and fit Gaussian Process age model when feasible.
- Produce subject predictions, voxelwise uncertainty proxy map, and input hash manifest.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `age_preds.csv`
   - required columns: `subject_id`, `actual_age`, `predicted_age`, `std_dev`, `status`, `reason`, `dataset_id`, `snapshot_tag`, `method`
2. `uncertainty.nii.gz`
   - finite, non-negative 3D map derived from real BOLD temporal variability
3. `input_manifest.csv`
   - required columns: `dataset_id`, `snapshot_tag`, `subject_id`, `run`, `remote_relpath`, `local_path`, `bytes`, `sha256`
4. `run_metadata.json`
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `processing_subject_count`, `processing_run_count`, `input_file_count`, `hash_manifest_sha256`

Hard Requirements
- No placeholders and no random/hash-invented outputs.
- If model preconditions are met, predictions/std must come from fitted model.
- If preconditions fail, emit structured `failed_precondition` rows with explicit `reason` and parseable required artifacts (`predicted_age/std_dev = NA`).
- Manifest hashes must trace consumed input files.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
