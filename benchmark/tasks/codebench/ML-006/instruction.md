Task: Perform nested cross-validation with hyperparameter tuning for ADHD prediction (ML-006)

    Scope
    - Category: Machine Learning
    - Dataset source: Nilearn
    - Dataset ID: fetch_adhd
    - Strict execution benchmark: outputs must be derived from real discovered inputs.

    Goal
    - Produce required outputs and provenance from real dataset files.

    Output Location
    - Write outputs to `${OUTPUT_DIR}` (default `/app/output`).

    Required Primary Outputs
    1. `cv_results.csv` (csv)
   - Required columns: record_id, fold, task_id, dataset_id, source_path, metric_name, metric_value, status, reason
2. `param_grid_search.json` (json)
   - Required keys: task_id, dataset_source, dataset_id, status, reason, method, records_count

    Required Provenance Outputs
    - `input_manifest.csv` with columns: `dataset_id,source_path,bytes,sha256`
    - `run_metadata.json` with keys:
      `task_id,dataset_source,dataset_id,status,reason,method,n_input_files,n_subjects,records_count,bytes_total,hash_manifest_sha256`

    Hard Requirements
    - No random-value fabrication.
    - Success branch must derive outputs from discovered input files.
    - Hash manifest must match consumed files.

    Fail-fast
    - If required inputs are missing/unreadable, emit `status=failed_precondition`
      with explicit reason while still writing parseable required outputs.
