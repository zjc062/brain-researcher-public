Task: Compute graph theory metrics (clustering, path length) from ABIDE connectivity (CONN-007)

Scope
- This is an execution-focused benchmark task.
- Dataset source: `Nilearn`.
- Dataset identifier: `fetch_abide_pcp`.
- Dual-mode behavior is required: real-compute when ABIDE fetch succeeds, fail-fast with explicit metadata when prerequisites are missing.

Goal
- Build subject-level ABIDE connectivity matrices.
- Compute graph metrics (`mean_degree`, `density`, `clustering_coeff`, `path_length`).
- Estimate small-world sigma against a random-graph baseline.

Input Requirements
- Real-compute mode requires:
  - successful ABIDE fetch for both `DX_GROUP=1` and `DX_GROUP=2`
  - at least 2 valid subjects per group
  - valid atlas-extracted connectivity matrices with consistent shape

Output Location
- Write outputs to `${OUTPUT_DIR}`.
- If unset, default to `/app/output`.

Required Outputs
1) `graph_metrics.csv`
- type: `csv`
- required columns:
  - `subject_id`, `dx_group`, `mean_degree`, `density`, `clustering_coeff`, `path_length`

2) `small_world_sigma.txt`
- type: `text`
- single numeric value (`sigma > 0` in `ok` mode)

Run Metadata
- Always emit `run_metadata.json` with:
  - `task_id`, `dataset_source`, `dataset_id`
  - `status` in `{ok, failed_precondition}`
  - explicit `reason`
- In `ok` mode include: `n_subjects`, `group_subject_counts`, `sigma`, `c_obs`, `l_obs`, `c_rand`, `l_rand`.

Pass Criteria
- Required outputs exist and parse in both modes.
- In `ok` mode, graph metrics ranges and sigma consistency checks pass.
- In `failed_precondition` mode, failure is explicit and machine-checkable via `run_metadata.json`.

Expected Results
- Real computed graph-theory outputs from ABIDE connectivity when prerequisites are met.
- Deterministic fail-fast artifacts with clear reason when prerequisites are unavailable.
