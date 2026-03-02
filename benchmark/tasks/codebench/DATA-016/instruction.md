Task: Generate quality assurance report for OASIS VBM dataset (DATA-016)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `Nilearn`.
- Dataset identifier: `fetch_oasis_vbm`.

Goal
- Fetch OASIS VBM data via `nilearn.datasets.fetch_oasis_vbm`.
- Compute subject-level QA checks from real input volumes:
  - missing modality checks (GM/WM presence)
  - low-signal checks from non-zero voxel ratio
  - intensity outlier checks from cohort statistics
  - shape/normalization consistency checks
  - GM/WM overlap-based registration outlier checks
- Produce machine-checkable QA outputs with explicit thresholds and traceability.

Input Requirements
- Resolve dataset from mounted cache when available.
- Default cache root should be `/task/cache` when writable.
- Do not fabricate synthetic image/table placeholders.
- If dataset cannot be resolved, return explicit `failed_precondition` with reason.

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.

Required Outputs
1) `qa_report.html`
   - type: `html`
2) `flagged_subjects.csv`
   - type: `csv`
   - required columns:
     - `subject_id`
     - `issue_code`
     - `severity`
     - `metric_name`
     - `metric_value`
     - `threshold`
     - `details`
     - `gm_path`
     - `wm_path`

Pass Criteria
- Required files exist and parse cleanly.
- `run_metadata.json` records `status` and `reason`.
- If `status=ok`:
  - QA metrics come from fetched OASIS inputs.
  - CSV rows follow schema and use non-placeholder values.
  - HTML report includes dataset-level summary and thresholded checks.
- If `status=failed_precondition`:
  - CSV and HTML clearly encode the failure reason.
  - No fake successful QA outputs are emitted.

Expected Results
- Real computed QA artifacts from OASIS VBM inputs when input resolution succeeds.
- Explicit fail-fast artifacts when dataset fetch/cache preconditions are not met.
