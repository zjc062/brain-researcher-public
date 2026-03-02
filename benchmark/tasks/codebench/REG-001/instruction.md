Task: Perform ANTs-SyN-style nonlinear registration to MNI152 for Haxby anatomical MRI (REG-001)

Scope
- Category: Registration (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds000105
- Strict mode: use real dataset inputs; no placeholder artifacts; no random fabricated values.

Goal
- Resolve a real `sub-*/anat/*_T1w.nii.gz` from the latest ds000105 snapshot.
- Register that T1w image into MNI152 space.
- Produce a nonlinear warp proxy map computed from the registered image and template (data-derived).

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `registered_T1w.nii.gz`
   - type: nifti
   - expected: non-empty 3D image in template space
2. `composite_warp.nii.gz`
   - type: nifti
   - expected: non-empty nonnegative warp/intensity-difference proxy map
3. `run_metadata.json`
   - type: json
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `subject_id`

Hard Requirements
- Do not emit synthetic placeholder files.
- Compute outputs from real ds000105 file content.
- Record traceability fields in `run_metadata.json`.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
