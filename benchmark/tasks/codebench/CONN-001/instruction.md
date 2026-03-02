Task: Compute resting-state functional connectivity using MSDL atlas on ADHD dataset (CONN-001)

Scope
- This is an execution-focused benchmark task.
- Dataset source: `OpenNeuro`.
- Dataset identifier: `ds002424`.
- Dual-mode behavior is required: real-compute when OpenNeuro access succeeds, fail-fast with explicit metadata when prerequisites are missing.

Goal
- Query OpenNeuro `ds002424` latest snapshot and discover valid BOLD files with ADHD labels.
- Compute subject-level connectivity matrices using MSDL atlas.
- Export group-average connectivity matrix plus ADHD vs control summary table.

Input Requirements
- Real-compute mode requires:
  - successful OpenNeuro GraphQL snapshot query
  - accessible `participants.tsv` containing `participant_id` and `ADHD_diagnosis`
  - at least one valid subject from each diagnosis group (`0`, `1`) with BOLD data

Output Location
- Write outputs to `${OUTPUT_DIR}`.
- If unset, default to `/app/output`.

Required Outputs
1) `connectivity_matrix.npy`
- type: `file` (NumPy `.npy`)
- 2D square symmetric matrix with diagonal approximately 1.0 (in `ok` mode)

2) `group_comparison.csv`
- type: `csv`
- required columns:
  - `group_label`, `dx_group`, `n_subjects`
  - `mean_edge_connectivity`, `std_edge_connectivity`, `subject_ids`
- exactly two rows (`dx_group` in `{0,1}`) in `ok` mode

Run Metadata
- Always emit `run_metadata.json` with:
  - `task_id`, `dataset_source`, `dataset_id`
  - `status` in `{ok, failed_precondition}`
  - explicit `reason`
- In `ok` mode include traceability fields:
  - `snapshot_tag`, `used_subject_ids`, `used_file_paths`, `group_subject_counts`, `matrix_upper_mean`

Pass Criteria
- Required outputs exist and parse in both modes.
- In `ok` mode, outputs satisfy strict schema + semantic checks and are computed from real `ds002424` inputs.
- In `failed_precondition` mode, failure is explicit and machine-checkable via `run_metadata.json`.

Expected Results
- Real computed connectivity artifacts when OpenNeuro access/prerequisites are available.
- Deterministic fail-fast artifacts with clear reason when prerequisites are unavailable.
