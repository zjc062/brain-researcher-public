Task: Test-retest reliability ICC (true voxelwise with fail-fast) (OPENNEURO-CONN-008_B)

Scope
- Category: Connectivity Analysis (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds000030
- Strict mode: real BOLD NIfTI + deterministic preflight + hash traceability.

Goal
- Download real ds000030 BOLD files and check repeat-scan feasibility.
- If preconditions fail, return structured `failed_precondition` outputs.
- If preconditions pass, compute edge-wise ICC from repeated runs.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `icc_results.csv`
   - required columns: `connection_id`, `icc_value`, `ci_95_low`, `ci_95_high`, `mean_icc`, `status`, `reason`, `subjects_included`, `repeat_subjects`, `bold_files`, `dataset_id`, `snapshot_tag`, `method`
2. `reliability_map.nii.gz`
3. `input_manifest.csv`
4. `run_metadata.json`

Hard Requirements
- No synthetic placeholders, no random fabricated values.
- Preflight decision must be based on real input counts.
- `icc_results.csv` and `run_metadata.json` status/reason must match.

Fail-fast
- If `subjects < 10` or `repeat_subjects < 10` or `bold_files == 0`, emit `failed_precondition` outputs and do not force ICC statistics.
