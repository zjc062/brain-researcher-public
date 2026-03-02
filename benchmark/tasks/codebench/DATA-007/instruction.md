Task: Create dataset splits (train/val/test) for OpenfMRI cohort (DATA-007)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `OpenNeuro`.
- Dataset identifier: `ds000030`.
- This task is dual-mode: perform stratified split when feasible, otherwise explicit fail-fast.

Goal
- Resolve subject metadata for `ds000030` from OpenNeuro latest snapshot.
- Build subject-level train/val/test splits (target 80/10/10) with random seed 42.
- Require stratification by sex and age bins when sample size supports it.
- If prerequisites are insufficient for valid stratified split, fail-fast with explicit reason.

Input Requirements
- Query OpenNeuro GraphQL for latest snapshot files.
- Use `participants.tsv` to derive `subject_id`, `age`, and `sex`.
- Subject IDs in split files must map to dataset subjects.

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.

Required Outputs
1) `train_subjects.txt`
   - type: `text`
2) `val_subjects.txt`
   - type: `text`
3) `test_subjects.txt`
   - type: `text`

Pass Criteria
- Required split files exist and are non-empty.
- `run_metadata.json` contains explicit `status` and `reason`.
- If `status=ok`: splits are mutually exclusive and counts align with target proportions.
- If `status=failed_precondition`: each split file records fail-fast reason explicitly.

Expected Results
- Real split assignment from dataset metadata when feasible.
- Deterministic fail-fast artifacts when stratified split prerequisites are unmet.
