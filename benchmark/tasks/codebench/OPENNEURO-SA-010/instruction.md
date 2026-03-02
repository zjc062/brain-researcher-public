Task: Lifespan Quadratic Age Modeling (true BOLD-derived metric) (OPENNEURO-SA-010)

Scope
- Category: Statistical Analysis (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds000030
- Strict mode: real BOLD NIfTI + participant metadata + deterministic quadratic fit.

Goal
- Resolve real ds000030 BOLD runs and participant ages.
- Compute subject-level connectivity proxy from atlas-extracted BOLD time-series.
- Fit quadratic age model (`age`, `age^2`) when preconditions are met.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `age_model_results.csv`
   - required columns: `connection`, `age_squared_p`, `beta_age`, `beta_age2`, `status`, `reason`, `subjects_included`, `sites_included`, `age_min`, `age_max`, `age_span`, `runs_used`, `dataset_id`, `snapshot_tag`, `method`
2. `input_manifest.csv`
   - required columns: `dataset_id`, `snapshot_tag`, `subject_id`, `session`, `run`, `remote_relpath`, `local_path`, `bytes`, `sha256`
3. `run_metadata.json`
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `subjects_included`, `sites_included`, `age_span`, `hash_manifest_sha256`

Hard Requirements
- No synthetic placeholders, no random fabricated values.
- If preconditions pass, `age_squared_p` must come from real fitted model statistics.
- If preconditions fail, return structured `failed_precondition` row with `NA` stats.
- Manifest and metadata must trace real input files.

Fail-fast
- When sample/site/age-span preconditions fail, emit `failed_precondition` and do not fabricate model p-values.
