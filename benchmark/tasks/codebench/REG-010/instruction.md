Task: Perform inverse-normalization-style projection from MNI to Miyawaki native space (REG-010)

Scope
- Category: Registration (execution task)
- Dataset source: Nilearn
- Dataset ID: `fetch_miyawaki2008`
- Strict mode: use real dataset inputs; no placeholder artifacts; no random fabricated values.

Goal
- Fetch Miyawaki native-space background image.
- Use MNI152 template as source space and resample into native space.
- Compute an inverse-warp proxy magnitude map from affine coordinate mapping.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `native_space_results.nii.gz`
   - type: nifti
   - expected: non-empty 3D resampled MNI result in native space
2. `inverse_warp.nii.gz`
   - type: nifti
   - expected: non-empty nonnegative inverse-warp proxy map
3. `run_metadata.json`
   - type: json
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `warp_mean`

Hard Requirements
- Do not emit synthetic placeholder files.
- Compute outputs from real fetched dataset content.
- Keep spatial/statistical traceability in `run_metadata.json`.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
