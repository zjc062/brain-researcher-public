Task: Haxby 8-way searchlight-style decoding map (true BOLD+events) (OPENNEURO-ML-005)

Scope
- Category: Machine Learning (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds000105
- Strict mode: real BOLD NIfTI + events TSV + deterministic decoding proxy.

Goal
- Resolve real ds000105 object-viewing BOLD/events run pairs.
- Compute an 8-way decoding-style voxel discriminability map from real event-labeled volumes.
- Emit map + metrics + hash-traceable input manifest.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `searchlight_map.nii.gz`
   - valid 3D NIfTI with finite values in `[0, 1]`
2. `results.json`
   - required keys: `dataset_id`, `snapshot_tag`, `subject_id`, `run`, `chance_level`, `mean_accuracy`, `n_trials`, `n_categories`, `status`, `reason`, `method`
3. `input_manifest.csv`
   - required columns: `dataset_id`, `snapshot_tag`, `subject_id`, `run`, `bold_relpath`, `events_relpath`, `bold_local_path`, `events_local_path`, `bold_bytes`, `events_bytes`, `bold_sha256`, `events_sha256`
4. `run_metadata.json`
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `processing_subject_count`, `processing_run_count`, `input_file_count`, `hash_manifest_sha256`

Hard Requirements
- No placeholders and no random/hash-invented metrics.
- Decode-map values must come from real BOLD+events computations.
- Manifest hashes must trace consumed input files.
- `results.json` and `run_metadata.json` must be mutually consistent.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
