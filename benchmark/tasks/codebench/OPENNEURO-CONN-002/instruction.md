Task: 7T resting-state DMN functional connectivity (true voxelwise) (OPENNEURO-CONN-002)

Scope
- Category: Connectivity Analysis (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds001168
- Strict mode: real BOLD NIfTI + atlas time-series extraction + file-hash traceability.

Goal
- Download real ds001168 BOLD files.
- Extract atlas time-series (MSDL), compute subject-level DMN connectivity matrices.
- Produce matrix bundle, subject summary, input hash manifest, and run metadata.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `subject_connectivity_matrices.npz`
2. `dmn_summary.csv`
   - required columns: `subject_id`, `n_runs`, `n_timepoints`, `mean_dmn_conn`, `std_dmn_conn`, `n_edges`
3. `input_manifest.csv`
   - required columns: `dataset_id`, `snapshot_tag`, `subject_id`, `session`, `run`, `remote_relpath`, `local_path`, `bytes`, `sha256`
4. `run_metadata.json`
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `processing_subject_count`, `processing_run_count`, `hash_manifest_sha256`

Hard Requirements
- No synthetic placeholders, no random fabricated values.
- Matrix and summary must be cross-consistent by subject.
- Hash manifest must trace all consumed input files.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
