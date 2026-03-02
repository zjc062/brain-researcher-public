Task: Compute evoked responses to auditory and visual stimuli in MNE sample (ELEC-003)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `Provided`.
- Dataset identifier: `mne_sample_dataset`.
- This task is dual-mode: real-compute when inputs exist, explicit fail-fast when prerequisites are missing.

Goal
- Resolve mounted inputs from `/task/cache/mne_sample_dataset` (or equivalent mounted input paths).
- Use raw data plus events to compute auditory and visual evoked responses.
- Export separate FIF files and a comparison plot.
- If required inputs are missing, fail-fast with explicit `status`/`reason` and reproducible artifacts.

Input Requirements
- Candidate input roots: `${INPUT_DIR}`, `/task/cache/mne_sample_dataset`, `/task/input/mne_sample_dataset`, `/app/input/mne_sample_dataset`.
- Real-compute mode requires:
  - `sample_audvis_raw.fif`
  - `sample_audvis_raw-eve.fif`

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.

Required Outputs
1) `auditory_evoked.fif`
   - type: `file`

2) `visual_evoked.fif`
   - type: `file`

3) `evoked_plot.png`
   - type: `png`
   - min size: 300x300

Pass Criteria
- Required files exist and parse.
- `run_metadata.json` declares `status` and `reason`.
- If `status=ok`, evoked objects have positive nave and matching channel dimensions.
- If `status=failed_precondition`, reason is explicit and artifacts remain valid.

Expected Results
- Real computed evoked-response outputs when prerequisites are satisfied.
- Deterministic fail-fast artifacts when prerequisites are unmet.
