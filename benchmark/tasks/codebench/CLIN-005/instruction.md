Task: Estimate brain-age gap from structural MRI in OASIS VBM (CLIN-005)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `Nilearn`.
- Dataset identifier: `fetch_oasis_vbm`.
- This task uses deterministic feature-based regression computed from OASIS inputs.

Goal
- Fetch OASIS VBM images and subject ages.
- Extract robust voxel-intensity features and run deterministic regression inference.
- Compute brain-age gap (`predicted_age - chronological_age`) per subject.
- Summarize age-gap distribution as an image.

Input Requirements
- Fetch OASIS VBM via `nilearn.datasets.fetch_oasis_vbm`.
- Use age labels from `ext_vars`.
- If feature extraction or regression inference cannot be completed, emit explicit `failed_precondition`.

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.
- Verifier may set `FORCE_FAILFAST=1` to validate deterministic fail-fast behavior.

Required Outputs
1) `predicted_ages.csv`
   - type: `csv`
   - required columns:
     - `subject_id`
     - `chronological_age`
     - `predicted_age`
     - `brain_age_gap`
     - `split`

2) `age_gap_distribution.png`
   - type: `png`
   - non-empty distribution plot

Pass Criteria
- Both required files exist and parse.
- `run_metadata.json` must contain `status` and `reason`.
- If `status=ok`:
  - CSV has non-empty rows with valid ages and exact `brain_age_gap` arithmetic.
  - metadata includes model provenance fields (`model_name`, `model_version`, `model_source_type`, `model_source`).
- If `status=failed_precondition`:
  - CSV and metadata contain explicit failure reason.
  - outputs remain parseable and reproducible.

Expected Results
- Real data-derived regression outputs when input prerequisites are satisfied.
- Deterministic fail-fast artifacts when feature extraction or inference preconditions are unmet.
