Task: Fail-fast preflight validation for missing required inputs (DATA-017)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `Provided`.
- Dataset identifier: `custom_missing_modalities`.
- Preserve semantic intent from the benchmark row while producing valid output artifacts.

Goal
- Resolve mounted input data from `/task/cache/custom_missing_modalities`.
- Accept equivalent mounted paths when provided by the runner (for example `${INPUT_DIR}`, `/task/input/custom_missing_modalities`, or `/app/input/custom_missing_modalities`).
- This is an intentional fail-fast preflight task: validate required modalities and report missing inputs.
- Do not fabricate replacement data or continue downstream modeling when required modalities are absent.

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.

Required Outputs
1) `preflight_check.json`
   - type: `json`
   - required keys: `status`, `required_inputs`, `missing_inputs`, `checked_paths`
2) `fail_fast_reason.txt`
   - type: `text`

Pass Criteria (Benchmark Contract)
- Preconditions are checked against `/task/cache/custom_missing_modalities` (or equivalent mounted path) and fail-fast status/reason are explicit.

Expected Results (Benchmark Contract)
- Structured fail-fast artifacts that enumerate missing required inputs from mounted data.
