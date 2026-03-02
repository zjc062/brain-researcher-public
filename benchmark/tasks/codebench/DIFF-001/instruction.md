Task: Preprocess diffusion MRI with motion/eddy correction proxy (DIFF-001)

Scope
- This is an execution-focused benchmark task.
- Dataset source: `Provided`.
- Dataset identifier: `custom_dwi_bids`.
- Dual-mode behavior is required: real-compute when input exists, fail-fast with explicit metadata when prerequisites are missing.

Goal
- Resolve mounted input roots (for example `${INPUT_DIR}`, `/task/cache/custom_dwi_bids`, `/task/input/custom_dwi_bids`, `/app/input/custom_dwi_bids`).
- Locate one DWI NIfTI (`*_dwi.nii.gz`) and its `.bval` sidecar.
- Perform deterministic volume-wise motion/intensity correction and write corrected DWI output.

Input Requirements
- Real-compute mode requires:
  - one DWI file (`*_dwi.nii.gz`)
  - one matching b-value file (`*.bval`)

Output Location
- Write outputs to `${OUTPUT_DIR}`.
- If unset, default to `/app/output`.

Required Outputs
1) `corrected_dwi.nii.gz`
- type: `nifti`
- real-compute mode: corrected 4D DWI image
- fail-fast mode: valid placeholder NIfTI

2) `eddy_movement.txt`
- type: `text/csv`
- header required: `volume,bval,shift_x,shift_y,shift_z,scale`
- one row per DWI volume

Run Metadata
- Always emit `run_metadata.json` with:
  - `task_id`, `dataset_source`, `dataset_id`
  - `status` in `{ok, failed_precondition}`
  - explicit `reason`
  - `records_count`, `bytes_total`, `checked_paths`

Pass Criteria
- Required outputs exist and parse.
- Motion table row count matches DWI volume count.
- `run_metadata.json` is internally consistent with outputs.
- In `ok` mode outputs are computed from mounted DWI input (not static placeholders).

Expected Results
- Real computed motion/eddy-corrected DWI outputs when input is present.
- Deterministic, parseable fail-fast artifacts when input is missing/incomplete.
