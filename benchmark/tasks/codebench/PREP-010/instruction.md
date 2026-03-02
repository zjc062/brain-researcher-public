Task: Run multi-echo combination and T2* estimation (PREP-010)

Scope
- Category: Preprocessing (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds000216
- Strict mode: use real dataset inputs; no placeholder artifacts; no fabricated random outputs.

Goal
- Resolve a real multi-echo BOLD run group from ds000216.
- Combine echoes into a single BOLD timeseries using echo-aware weighting.
- Estimate voxelwise T2* map from the same echo set.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `combined_bold.nii.gz`
   - type: nifti
   - expected: non-empty 4D combined BOLD image
2. `t2star_map.nii.gz`
   - type: nifti
   - expected: non-empty 3D T2* map aligned to combined BOLD space
3. `run_metadata.json`
   - type: json
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `subject_id`

Hard Requirements
- Do not emit synthetic placeholder files.
- Compute outputs from real ds000216 multi-echo input files.
- Metadata must report `echo_count` and `echo_indices` consistent with used inputs.
- T2* values must be finite and within a physiologically plausible bounded range.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
