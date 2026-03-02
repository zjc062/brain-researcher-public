Task: Perform ICA decomposition to identify eye blink components in MNE sample (ELEC-002)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `Provided`.
- Dataset identifier: `mne_sample_dataset`.
- This task is dual-mode: real-compute when inputs exist, explicit fail-fast when prerequisites are missing.

Goal
- Resolve mounted inputs from `/task/cache/mne_sample_dataset` (or equivalent mounted input paths).
- Locate sample raw FIF file and perform ICA decomposition on MEG channels.
- Identify candidate eye-blink components using EOG correlation when EOG channels exist.
- If required inputs are missing, fail-fast with explicit `status`/`reason` and reproducible artifacts.

Input Requirements
- Candidate input roots: `${INPUT_DIR}`, `/task/cache/mne_sample_dataset`, `/task/input/mne_sample_dataset`, `/app/input/mne_sample_dataset`.
- Real-compute mode requires:
  - `sample_audvis_raw.fif`

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.

Required Outputs
1) `ica_solution.fif`
   - type: `file`
   - real-compute mode: fitted ICA object
   - fail-fast mode: valid placeholder ICA artifact

2) `component_topographies.png`
   - type: `png`
   - min size: 300x300

Pass Criteria
- Required files exist and parse.
- `run_metadata.json` declares `status` and `reason`.
- If `status=ok`, ICA has multiple components and topography image is non-trivial.
- If `status=failed_precondition`, reason is explicit and artifacts remain valid.

Expected Results
- Real computed ICA outputs when prerequisites are satisfied.
- Deterministic fail-fast artifacts when prerequisites are unmet.
