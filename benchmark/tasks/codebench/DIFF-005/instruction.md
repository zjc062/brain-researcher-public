Task: Compute FA-derived structural connectome with AAL labels (DIFF-005)

Scope
- This is an execution-focused benchmark task.
- Dataset source: `Provided`.
- Dataset identifier: `custom_dwi_aal_atlas`.
- Dual-mode behavior is required: real-compute when input exists, fail-fast with explicit metadata when prerequisites are missing.

Goal
- Resolve mounted input roots (for example `${INPUT_DIR}`, `/task/cache/custom_dwi_aal_atlas`, `/task/input/custom_dwi_aal_atlas`, `/app/input/custom_dwi_aal_atlas`).
- Use DWI + bval/bvec to estimate FA.
- Use provided AAL atlas labels to aggregate region-level statistics and compute a symmetric edge table.
- Render a connectome heatmap figure.

Input Requirements
- Real-compute mode requires:
  - one DWI file (`*_dwi.nii.gz`)
  - one b-value file (`*.bval`)
  - one b-vector file (`*.bvec`)
  - one atlas file (`aal_atlas_resampled.nii.gz`)

Output Location
- Write outputs to `${OUTPUT_DIR}`.
- If unset, default to `/app/output`.

Required Outputs
1) `structural_connectome.csv`
- type: `csv`
- required columns:
  - `region_i`, `region_j`
  - `index_i`, `index_j`
  - `weight`
  - `mean_fa_i`, `mean_fa_j`
  - `n_voxels_i`, `n_voxels_j`

2) `connectome_plot.png`
- type: `png`
- minimum size: `300x300`

Run Metadata
- Always emit `run_metadata.json` with:
  - `task_id`, `dataset_source`, `dataset_id`
  - `status` in `{ok, failed_precondition}`
  - explicit `reason`
  - `records_count`, `bytes_total`, `checked_paths`
  - summary metrics (for example `n_regions`, `n_edges`, `mean_edge_weight`)

Pass Criteria
- Required outputs exist and parse.
- CSV schema is explicit and non-empty.
- `run_metadata.json` is internally consistent with CSV edge count/statistics.
- In `ok` mode outputs are computed from mounted diffusion + atlas inputs (not static placeholders).

Expected Results
- Real computed connectome outputs when input is present.
- Deterministic, parseable fail-fast artifacts when input is missing/incomplete.
