Task: Map lesion locations to behavioral deficits using VLSM (CLIN-006)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `Provided`.
- Dataset identifier: `simulated_lesion_symptom_data`.
- This task is dual-mode: real-compute when inputs exist, explicit fail-fast when prerequisites are missing.
- Do not use public fallback datasets or synthetic pseudo-label replacement when required inputs are absent.

Goal
- Resolve mounted inputs from `/task/cache/simulated_lesion_symptom_data` (or equivalent mounted input paths).
- If lesion maps + behavioral deficit table are present, run voxel-wise lesion-deficit association.
- If required inputs are missing, fail-fast with explicit `status`/`reason` and reproducible failure artifacts.

Input Requirements
- Candidate input roots: `${INPUT_DIR}`, `/task/cache/simulated_lesion_symptom_data`, `/task/input/simulated_lesion_symptom_data`, `/app/input/simulated_lesion_symptom_data`.
- Real-compute mode requires:
  - subject-level lesion NIfTI files
  - behavioral table containing subject IDs and a numeric deficit variable
  - at least 4 matched subjects

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.
- Verifier may set `FORCE_FAILFAST=1` to validate deterministic fail-fast behavior.

Required Outputs
1) `vlsm_map.nii.gz`
   - type: `nifti`
   - real-compute mode: voxel-wise association map derived from lesion data
   - fail-fast mode: explicit failure artifact (loadable NIfTI)

2) `deficit_correlations.csv`
   - type: `csv`
   - required columns:
     - `voxel_index`
     - `x`
     - `y`
     - `z`
     - `correlation_r`
     - `t_stat`
     - `p_value`
     - `n_subjects`
     - `status`
     - `reason`

Pass Criteria
- Both required files exist and parse.
- `deficit_correlations.csv` has required columns.
- `run_metadata.json` must declare `status` and `reason`.
- If `status=ok`, outputs must reflect real matched-input analysis (not placeholders).
- If `status=failed_precondition`, failure reason must be explicit and identical across CSV and metadata.

Expected Results
- Real-compute output when prerequisites are satisfied.
- Deterministic fail-fast artifacts when prerequisites are unmet.
