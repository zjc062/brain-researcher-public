Task: Apply temporal band-pass filtering (0.01-0.10 Hz) to resting-state fMRI (PREP-009)

Scope
- Category: Preprocessing (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds000030
- Strict mode: use real dataset inputs; no placeholder artifacts; no fabricated random outputs.

Goal
- Resolve a real BOLD run from ds000030 (prefer resting-state runs when available).
- Apply temporal filtering to preserve 0.01-0.10 Hz signal components.
- Produce filtered BOLD and a power-spectrum diagnostic image.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `filtered_bold.nii.gz`
   - type: nifti
   - expected: non-empty 4D band-pass filtered BOLD image
2. `power_spectrum.png`
   - type: png
   - expected: valid non-empty diagnostic plot
3. `run_metadata.json`
   - type: json
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`
   - when `status=ok`, include: `snapshot_tag`, `subject_id`

Hard Requirements
- Do not emit synthetic placeholder files.
- Compute outputs from real ds000030 file content when available.
- When `status=ok`, metadata must report `tr`, `low_hz`, `high_hz`, `pre_highfreq_ratio`, `post_highfreq_ratio`.
- When `status=ok`, `post_highfreq_ratio` should be lower than `pre_highfreq_ratio`.

Fail-fast
- If no valid BOLD run is found or required fetch/parse fails, emit `status=failed_precondition`
  with explicit reason while still writing parseable required outputs.
