Task: Generate pseudo-FOD spherical-harmonic representation from DTI (DIFF-011)

Scope
- This is an execution-focused benchmark task.
- Dataset source: `Provided`.
- Dataset identifier: `custom_dwi_data`.
- Dual-mode behavior is required: real-compute when input exists, fail-fast with explicit metadata when prerequisites are missing.

Goal
- Resolve mounted input roots (for example `${INPUT_DIR}`, `/task/cache/custom_dwi_data`, `/task/input/custom_dwi_data`, `/app/input/custom_dwi_data`).
- Locate one DWI NIfTI and matching `.bval` + `.bvec` files.
- Fit a tensor model, estimate principal orientation, and export a deterministic pseudo-FOD SH representation.

Input Requirements
- Real-compute mode requires:
  - one DWI file (`*_dwi.nii.gz`)
  - one b-value file (`*.bval`)
  - one b-vector file (`*.bvec`)
  - enough volumes for tensor fitting (>= 7)

Output Location
- Write outputs to `${OUTPUT_DIR}`.
- If unset, default to `/app/output`.

Required Outputs
1) `fod.mif`
- type: `file`
- must include MIF-style header with `dim:` for `(X,Y,Z,C)`

2) `fod_peaks.nii.gz`
- type: `nifti`
- expected shape: `(X,Y,Z,3)` orientation peak vectors

Run Metadata
- Always emit `run_metadata.json` with:
  - `task_id`, `dataset_source`, `dataset_id`
  - `status` in `{ok, failed_precondition}`
  - explicit `reason`
  - `records_count`, `bytes_total`, `checked_paths`
  - summary metrics (for example `fod_dim`, `mean_peak_norm`)

Pass Criteria
- Required outputs exist and parse.
- MIF header dimensions and peak-map dimensions are consistent.
- `run_metadata.json` is internally consistent with outputs.
- In `ok` mode outputs are computed from mounted diffusion input (not static placeholders).

Expected Results
- Real computed pseudo-FOD outputs when input is present.
- Deterministic, parseable fail-fast artifacts when input is missing/incomplete.
