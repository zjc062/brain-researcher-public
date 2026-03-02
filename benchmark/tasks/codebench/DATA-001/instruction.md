Task: OpenNeuro metadata extraction for `ds000105` (Haxby)

Scope
- This task is about dataset metadata extraction only.
- No Nilearn modeling or image-level analysis is required.

Goal
- Query OpenNeuro for dataset `ds000105` and use its latest snapshot metadata.
- Generate exactly two output files:
  - `dataset_description.json`
  - `participants.tsv`

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.

Required Outputs
1) `dataset_description.json`
   - Valid JSON object.
   - Must include non-empty `Name`, `BIDSVersion`, and `DatasetDOI`.
   - `DatasetDOI` must correspond to `ds000105` (contains `openneuro.ds000105`).

2) `participants.tsv`
   - Valid TSV with header column `participant_id`.
   - IDs must be BIDS-style (`sub-...`), unique, and sorted.
   - Participant set must match subjects derived from the latest OpenNeuro snapshot
     file tree (i.e., `sub-*` top-level directories), not hand-written/invented.
