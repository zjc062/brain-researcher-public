Task: Run multi-modal registration of T1w anatomy to T2*-like functional reference for SPM multimodal (REG-005)

Scope
- Category: Registration (execution task)
- Dataset source: Nilearn
- Dataset ID: `fetch_spm_multimodal_fmri`
- Strict mode: use real dataset inputs; no placeholder artifacts; no random fabricated values.

Goal
- Fetch real SPM multimodal files (`anat` + `func1`).
- Build a T2*-like reference by averaging real functional volumes.
- Register anatomy into the functional reference space and emit affine matrix.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `t1_to_t2_matrix.mat`
   - type: mat/text matrix
   - expected: finite 4x4 affine transform (not identity)
2. `coregistered_t1.nii.gz`
   - type: nifti
   - expected: non-empty 3D image in functional-reference space
3. `run_metadata.json`
   - type: json
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `n_func_used`

Hard Requirements
- Do not emit synthetic placeholder files.
- Compute outputs from real fetched dataset files.
- Keep transform and data lineage traceable in `run_metadata.json`.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
