Task: Group ICA with test-retest stability (true voxelwise) (OPENNEURO-CONN-006)

Scope
- Category: Connectivity Analysis (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds001168
- Strict mode: real BOLD NIfTI + atlas time-series extraction + FastICA.

Goal
- Download real ds001168 BOLD files.
- Extract atlas time-series, fit 20-component ICA, produce component maps.
- Compute per-component stability statistics and per-run component summaries.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `ica_components.nii.gz`
2. `stats.csv`
   - required columns: `component_id`, `group_diff_t`, `stability_corr`, `component_mean`, `component_std`, `n_subjects`, `n_paired_subjects`, `snapshot_tag`, `method`
3. `component_timeseries.csv`
   - required columns: `subject_id`, `session`, `run_id`, `component_id`, `mean_abs_source`, `std_source`, `n_timepoints`
4. `input_manifest.csv`
5. `run_metadata.json`

Hard Requirements
- No synthetic placeholders, no random fabricated values.
- `ica_components.nii.gz` must be valid 4D data with exactly 20 components.
- Stats and component_timeseries must be internally consistent.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
