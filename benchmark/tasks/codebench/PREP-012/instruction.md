Task: Apply CompCor-like nuisance regression on Haxby BOLD (PREP-012)

Scope
- Category: Preprocessing (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds000105
- Strict mode: use real dataset inputs; no placeholder artifacts; no fabricated random outputs.

Goal
- Resolve a real BOLD run from ds000105.
- Derive nuisance components from noise-dominant voxels (CompCor-style PCA).
- Regress nuisance components and produce cleaned BOLD plus component table.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `cleaned_bold.nii.gz`
   - type: nifti
   - expected: non-empty 4D cleaned BOLD image
2. `compcor_components.tsv`
   - type: tsv
   - required columns: `timepoint`, `compcor_1`, `compcor_2`, `compcor_3`
3. `run_metadata.json`
   - type: json
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `subject_id`

Hard Requirements
- Do not emit synthetic placeholder files.
- Compute outputs from real ds000105 file content.
- Component table rows must align with BOLD timepoints.
- Metadata must report noise voxel count and explained variance ratio.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
