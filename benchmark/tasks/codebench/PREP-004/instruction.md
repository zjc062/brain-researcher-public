Task: Run volume-wise motion correction on Development fMRI (PREP-004)

Scope
- Category: Preprocessing (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds003592
- Strict mode: use real dataset inputs; no placeholder artifacts; no fabricated random outputs.

Goal
- Resolve a real BOLD run from ds003592.
- Estimate per-volume translations and align volumes to a reference volume.
- Produce motion-corrected BOLD and corresponding motion parameter table.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `motion_corrected_bold.nii.gz`
   - type: nifti
   - expected: non-empty 4D motion-corrected BOLD image
2. `motion_parameters.txt`
   - type: text
   - expected: one row per timepoint with 6 motion parameters
3. `run_metadata.json`
   - type: json
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `subject_id`

Hard Requirements
- Do not emit synthetic placeholder files.
- Compute outputs from real ds003592 file content.
- Motion parameter rows must align with BOLD timepoints.
- Record traceability and motion summary statistics in `run_metadata.json`.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
