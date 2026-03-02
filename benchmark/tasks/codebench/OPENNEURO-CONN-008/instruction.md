Task: ALFF/fALFF calculation (true voxelwise) (OPENNEURO-CONN-008)

Scope
- Category: Connectivity Analysis (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds001168
- Strict mode: real BOLD NIfTI voxelwise FFT + hash traceability.

Goal
- Download real ds001168 BOLD files.
- Compute voxelwise ALFF/fALFF maps in [0.01, 0.1] Hz band.
- Emit one ALFF/fALFF pair per processed subject and manifest all inputs.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `alff_maps/`
2. `falff_maps/`
3. `map_manifest.csv`
   - required columns: `subject_id`, `session`, `run_id`, `alff_file`, `falff_file`, `alff_mean`, `falff_mean`, `n_timepoints`, `tr`, `frequency_band`, `snapshot_tag`, `method`
4. `input_manifest.csv`
5. `run_metadata.json`

Hard Requirements
- No synthetic placeholders, no random fabricated values.
- Subject sets must match across ALFF, fALFF, and manifest.
- Frequency band declaration must be explicit and consistent.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
