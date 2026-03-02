Task: Extract time series from Yeo 7 networks and compute correlation matrix on NKI data (CONN-002)

Scope
- This is an execution-focused benchmark task.
- Dataset source: `Nilearn`.
- Dataset identifier: `fetch_surf_nki_enhanced`.
- Dual-mode behavior is required: real-compute when Nilearn fetch succeeds, fail-fast with explicit metadata when prerequisites are missing.

Goal
- Fetch NKI enhanced surface fMRI and Yeo 7-network atlas data.
- Extract 7-network subject time series and compute a group mean 7x7 correlation matrix.
- Export CSV time series plus correlation heatmap.

Input Requirements
- Real-compute mode requires:
  - successful `fetch_surf_nki_enhanced` + Yeo atlas + fsaverage fetch
  - at least 3 subjects with valid left/right hemisphere time series
  - non-empty vertex coverage for all network IDs 1..7

Output Location
- Write outputs to `${OUTPUT_DIR}`.
- If unset, default to `/app/output`.

Required Outputs
1) `network_timeseries.csv`
- type: `csv`
- required columns:
  - `subject_id`, `timepoint`, `network_id`, `network_label`, `signal`
- must cover network IDs 1..7 in `ok` mode

2) `correlation_matrix.png`
- type: `png`
- non-empty heatmap derived from computed correlations

Run Metadata
- Always emit `run_metadata.json` with:
  - `task_id`, `dataset_source`, `dataset_id`
  - `status` in `{ok, failed_precondition}`
  - explicit `reason`
- In `ok` mode include traceability fields:
  - `used_subject_ids`, `n_rows_network_timeseries`, `n_networks`, `correlation_upper_mean`

Pass Criteria
- Required outputs exist and parse in both modes.
- In `ok` mode, CSV schema + network coverage + cross-file correlation checks pass.
- In `failed_precondition` mode, failure is explicit and machine-checkable via `run_metadata.json`.

Expected Results
- Real computed NKI/Yeo network signals and correlation heatmap when prerequisites are met.
- Deterministic fail-fast artifacts with clear reason when prerequisites are unavailable.
