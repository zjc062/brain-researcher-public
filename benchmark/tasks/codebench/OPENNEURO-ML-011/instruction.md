Task: ADHD feature selection with Elastic Net logistic model (real metadata features) (OPENNEURO-ML-011)

Scope
- Category: Machine Learning (execution task)
- Dataset source: OpenNeuro
- Dataset ID: ds002424
- Strict mode: real participants metadata -> deterministic feature engineering -> trained model.

Goal
- Build subject-level predictive features from real `participants.tsv` values.
- Train Elastic Net logistic model with CV model selection.
- Output top 50 weighted interactions and input hash traceability.

Output Location
- Write outputs to `${OUTPUT_DIR}` (default: `/app/output`).

Required Outputs
1. `top_features.csv`
   - required columns: `roi_1`, `roi_2`, `weight`, `dataset_id`, `snapshot_tag`, `subjects_used`, `best_c`, `best_l1_ratio`, `mean_auc`
   - exactly 50 rows sorted by `abs(weight)` descending
2. `input_manifest.csv`
   - required columns: `dataset_id`, `snapshot_tag`, `file_relpath`, `local_path`, `bytes`, `sha256`
3. `run_metadata.json`
   - required keys: `task_id`, `dataset_source`, `dataset_id`, `status`, `reason`, `snapshot_tag`, `n_subjects`, `n_edge_features`, `n_selected_features`, `mean_auc`, `hash_manifest_sha256`

Hard Requirements
- No placeholders and no synthetic fabricated features.
- Feature values must derive from real ds002424 participant metadata.
- Top-feature ranking must come from trained model coefficients.
- Manifest hashes must trace consumed input files.

Fail-fast
- fail-fast: if required mounted inputs are missing, write run_metadata.json with status=failed_precondition and reason describing missing inputs; do not emit synthetic placeholders.
