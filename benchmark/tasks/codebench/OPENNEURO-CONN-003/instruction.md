Task: ADHD vs control Network-Based Statistics (true voxelwise) (OPENNEURO-CONN-003)

Scope
- Category: Connectivity Analysis (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds002424
- Strict mode: real BOLD NIfTI + atlas time-series extraction + deterministic max-T correction.

Goal
- Download real ds002424 BOLD files and align with participants diagnosis labels.
- Compute subject-level FC, then edge-wise group statistics.
- Apply deterministic permutation max-T correction and output significant edges.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `nbs_results.txt`
2. `altered_edges.csv`
   - required columns: `roi_1`, `roi_2`, `t_stat`, `p_val`, `adhd_mean`, `control_mean`, `n_adhd`, `n_control`
3. `group_connectivity_stats.csv`
   - required columns: `roi_1`, `roi_2`, `t_stat`, `p_uncorrected`, `p_corrected`, `adhd_mean`, `control_mean`, `n_adhd`, `n_control`, `significant`
4. `input_manifest.csv`
5. `run_metadata.json`

Hard Requirements
- No synthetic placeholders, no random fabricated values.
- Group counts must match analyzed subject labels.
- Corrected p-values and significant edge counts must match summary.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
