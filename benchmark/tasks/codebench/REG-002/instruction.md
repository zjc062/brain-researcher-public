Task: Run FLIRT-style affine registration from ADHD-200 BOLD to structural MRI (REG-002)

Scope
- Category: Registration (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds002424
- Strict mode: use real dataset inputs; no placeholder artifacts; no random fabricated values.

Goal
- Resolve a real subject/session with both `anat/*_T1w.nii.gz` and `func/*_bold.nii.gz` from ds002424.
- Compute an affine transform matrix mapping BOLD reference volume to T1w space.
- Resample BOLD reference volume into T1w space.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `flirt_matrix.mat`
   - type: mat/text matrix
   - expected: finite 4x4 affine transform (not identity)
2. `coregistered_bold.nii.gz`
   - type: nifti
   - expected: non-empty 3D coregistered BOLD reference volume
3. `run_metadata.json`
   - type: json
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `subject_id`, `bold_timepoints`

Hard Requirements
- Do not emit synthetic placeholder files.
- Compute outputs from real ds002424 content.
- Keep transform and image statistics traceable via `run_metadata.json`.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
