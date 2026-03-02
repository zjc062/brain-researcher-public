Task: Miyawaki Visual Encoding Effect Size (true BOLD+events) (OPENNEURO-SA-007)

Scope
- Category: Statistical Analysis (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds000255
- Strict mode: real BOLD NIfTI + real events TSV + hash traceability.

Goal
- Resolve real ds000255 BOLD/event pairs from snapshot.
- Compute event-locked response effects from real global BOLD time-series.
- Report per-stimulus effect-size estimates (Cohen's d + CI) without synthetic placeholders.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `effect_sizes.csv`
   - required columns: `stimulus_id`, `cohens_d`, `ci_lower`, `ci_upper`, `n_samples`, `mean_effect`, `status`, `reason`, `subjects_included`, `runs_used`, `events_used`, `dataset_id`, `snapshot_tag`, `method`
2. `input_manifest.csv`
   - required columns: `dataset_id`, `snapshot_tag`, `subject_id`, `session`, `run`, `bold_relpath`, `events_relpath`, `bold_local_path`, `events_local_path`, `bold_bytes`, `events_bytes`, `bold_sha256`, `events_sha256`
3. `run_metadata.json`
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `processing_subject_count`, `processing_run_count`, `events_used`, `hash_manifest_sha256`

Hard Requirements
- No synthetic placeholders, no random fabricated values.
- `effect_sizes.csv` values must derive from real BOLD/event processing.
- `input_manifest.csv` must hash-trace all consumed files.
- `run_metadata.json` must be cross-consistent with output tables.

Fail-fast
- If no usable BOLD+events signal can be computed, emit structured `failed_precondition` output (not fake statistics).
