Task: Stimulus-correlated motion proxy on ds000255 (real BOLD+events) (OPENNEURO-QC-010)

Scope
- Category: Quality Control (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds000255
- Strict mode: real BOLD/event processing + hash traceability.

Goal
- Resolve real paired BOLD + events runs from OpenNeuro ds000255.
- Compute six motion-like trace correlations against event regressor per processed run.
- Emit row-level correlations, artifact summary, input manifest, and consistent metadata.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `motion_correlation.csv`
   - required columns: `subject_id`, `run`, `axis`, `correlation_r`, `p_value`, `status`, `reason`, `dataset_id`, `snapshot_tag`, `method`
2. `artifact_flag.json`
   - required keys: `dataset_id`, `snapshot_tag`, `artifact_detected`, `significant_pairs`, `status`, `reason`, `method`
3. `input_manifest.csv`
   - required columns: `dataset_id`, `snapshot_tag`, `subject_id`, `session`, `run`, `bold_relpath`, `events_relpath`, `bold_local_path`, `events_local_path`, `bold_bytes`, `events_bytes`, `bold_sha256`, `events_sha256`
4. `run_metadata.json`
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `processing_subject_count`, `processing_run_count`, `input_file_count`, `hash_manifest_sha256`

Hard Requirements
- No placeholder or hash-synthesized correlations.
- Correlation values must derive from real BOLD-derived traces + real event timing.
- Manifest hashes must trace all consumed files.
- JSON summary must be consistent with CSV-derived counts.

Fail-fast
- If no usable paired BOLD/events runs exist, emit structured `failed_precondition` outputs (not fake correlations).
