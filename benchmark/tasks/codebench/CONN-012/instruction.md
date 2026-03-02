Task: Perform edge-wise connectivity analysis comparing autism vs control in ABIDE (CONN-012)

Scope
- This is an execution-focused benchmark task.
- Dataset source: `Nilearn`.
- Dataset identifier: `fetch_abide_pcp`.
- Dual-mode behavior is required: real-compute when ABIDE fetch succeeds, fail-fast with explicit metadata when prerequisites are missing.

Goal
- Build ABIDE subject-level connectivity matrices.
- Perform edge-wise ASD vs control comparison.
- Export ranked edge statistics CSV and full t-statistics matrix.

Input Requirements
- Real-compute mode requires:
  - successful ABIDE fetch for both `DX_GROUP=1` and `DX_GROUP=2`
  - at least 2 valid subjects per group
  - consistent connectivity matrix dimensions across subjects

Output Location
- Write outputs to `${OUTPUT_DIR}`.
- If unset, default to `/app/output`.

Required Outputs
1) `significant_edges.csv`
- type: `csv`
- required columns:
  - `edge_i`, `edge_j`, `t_stat`, `p_value`, `mean_asd`, `mean_control`, `effect_size`, `significant`
- rows sorted by ascending `p_value` in `ok` mode

2) `edge_statistics.npy`
- type: `file` (NumPy `.npy`)
- square symmetric matrix of edge-wise t-statistics

Run Metadata
- Always emit `run_metadata.json` with:
  - `task_id`, `dataset_source`, `dataset_id`
  - `status` in `{ok, failed_precondition}`
  - explicit `reason`
- In `ok` mode include: `n_regions`, `n_subjects_asd`, `n_subjects_control`, `n_edges_total`, `n_significant`, `n_reported_edges`.

Pass Criteria
- Required outputs exist and parse in both modes.
- In `ok` mode, CSV numeric validity, matrix consistency, and cross-file traceability checks pass.
- In `failed_precondition` mode, failure is explicit and machine-checkable via `run_metadata.json`.

Expected Results
- Real computed ABIDE edge-wise statistics when prerequisites are met.
- Deterministic fail-fast artifacts with clear reason when prerequisites are unavailable.
