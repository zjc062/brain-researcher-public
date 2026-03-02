Task: Perform source localization using dSPM on auditory evoked responses (ELEC-005)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `Provided`.
- Dataset identifier: `mne_sample_dataset`.
- This task is dual-mode: real-compute when inputs exist, explicit fail-fast when prerequisites are missing.

Goal
- Resolve mounted inputs from `/task/cache/mne_sample_dataset` (or equivalent mounted input paths).
- Compute auditory evoked response from raw/events and apply dSPM inverse solution.
- Export left/right hemisphere source estimate files and summary plot.
- If required inputs are missing, fail-fast with explicit `status`/`reason` and reproducible artifacts.

Input Requirements
- Candidate input roots: `${INPUT_DIR}`, `/task/cache/mne_sample_dataset`, `/task/input/mne_sample_dataset`, `/app/input/mne_sample_dataset`.
- Real-compute mode requires:
  - `sample_audvis_raw.fif`
  - `sample_audvis_raw-eve.fif`
  - `sample_audvis-meg-oct-6-meg-inv.fif`

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.

Required Outputs
1) `auditory-lh.stc`
   - type: `file`

2) `auditory-rh.stc`
   - type: `file`

3) `source_plot.png`
   - type: `png`
   - min size: 300x300

Pass Criteria
- Required files exist and parse.
- `run_metadata.json` declares `status` and `reason`.
- If `status=ok`, STC files load as a valid pair and contain finite source data.
- If `status=failed_precondition`, reason is explicit and artifacts remain valid.

Expected Results
- Real computed source-localization outputs when prerequisites are satisfied.
- Deterministic fail-fast artifacts when prerequisites are unmet.
