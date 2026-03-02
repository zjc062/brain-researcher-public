Task: Identify treatment responders from baseline brain features (CLIN-014)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `Provided`.
- Dataset identifier: `simulated_treatment_dataset`.
- This task is dual-mode: real-compute when inputs exist, explicit fail-fast when prerequisites are missing.
- Do not use public fallback datasets or synthetic pseudo-label replacement when required inputs are absent.

Goal
- Resolve mounted inputs from `/task/cache/simulated_treatment_dataset` (or equivalent mounted input paths).
- If baseline MRI + responder labels are present, train a responder classifier and export model.
- Derive a predictive brain map from responder vs non-responder baseline differences.
- If required inputs are missing, fail-fast with explicit `status`/`reason` and reproducible artifacts.

Input Requirements
- Candidate input roots: `${INPUT_DIR}`, `/task/cache/simulated_treatment_dataset`, `/task/input/simulated_treatment_dataset`, `/app/input/simulated_treatment_dataset`.
- Real-compute mode requires:
  - a table with subject IDs and binary responder label
  - baseline NIfTI maps matched to subjects
  - at least 6 matched subjects and both classes represented

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.
- Verifier may set `FORCE_FAILFAST=1` to validate deterministic fail-fast behavior.

Required Outputs
1) `responder_model.pkl`
   - type: `pickle`
   - contains model parameters, feature schema, and training diagnostics

2) `predictive_map.nii.gz`
   - type: `nifti`
   - real-compute mode: derived map from group baseline differences
   - fail-fast mode: explicit failure artifact (loadable NIfTI)

Pass Criteria
- Both required files exist and parse.
- `run_metadata.json` must declare `status` and `reason`.
- If `status=ok`, model must include trained parameters and class coverage metadata.
- If `status=failed_precondition`, failure reason must be explicit and identical across model artifact and metadata.

Expected Results
- Real-compute artifacts when prerequisites are satisfied.
- Deterministic fail-fast artifacts when prerequisites are unmet.
