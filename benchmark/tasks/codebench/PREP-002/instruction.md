Task: Preprocess ADHD-200 resting-state with ICA-AROMA-style denoising (PREP-002)

Scope
- Category: Preprocessing (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds002424
- Strict mode: use real dataset inputs; no placeholder artifacts; no fabricated random outputs.

Goal
- Resolve a real BOLD run from ds002424.
- Compute ICA components from voxel time series and classify likely motion components.
- Produce non-aggressive denoised BOLD plus component table derived from real inputs.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `*_desc-smoothAROMAnonaggr_bold.nii.gz`
   - type: nifti_glob
   - expected: non-empty 4D denoised BOLD image
2. `mixing_matrix.tsv`
   - type: tsv
   - required columns: `component_id`, `variance_explained`, `hf_ratio`, `motion_corr`, `is_motion`, `n_timepoints`
3. `run_metadata.json`
   - type: json
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `subject_id`

Hard Requirements
- Do not emit synthetic placeholder files.
- Compute outputs from real ds002424 file content.
- Ensure at least one component is flagged as motion-related.
- Record traceability and summary statistics in `run_metadata.json`.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
