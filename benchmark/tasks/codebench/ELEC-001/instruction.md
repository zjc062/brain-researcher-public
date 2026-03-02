Task: Preprocess MNE sample MEG data with maxwell filtering and artifact removal (ELEC-001)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `Provided`.
- Dataset identifier: `mne_sample_dataset`.
- This task is dual-mode: real-compute when inputs exist, explicit fail-fast when prerequisites are missing.

Goal
- Resolve mounted inputs from `/task/cache/mne_sample_dataset` (or equivalent mounted input paths).
- Locate the MNE sample raw FIF file and SSS calibration/cross-talk files.
- In real-compute mode, run Maxwell filtering plus band-pass/notch filtering and export cleaned raw FIF.
- If required inputs are missing, fail-fast with explicit `status`/`reason` and reproducible artifacts.

Input Requirements
- Candidate input roots: `${INPUT_DIR}`, `/task/cache/mne_sample_dataset`, `/task/input/mne_sample_dataset`, `/app/input/mne_sample_dataset`.
- Real-compute mode requires:
  - `sample_audvis_raw.fif`
  - `sss_cal_mgh.dat`
  - `ct_sparse_mgh.fif`

Output Location
- Write deliverables to `${OUTPUT_DIR}`.
- If `OUTPUT_DIR` is unset, default to `/app/output`.

Required Outputs
1) `clean_raw.fif`
   - type: `file`
   - real-compute mode: Maxwell + filtered raw MEG data
   - fail-fast mode: valid placeholder FIF artifact

2) `preprocessing_report.html`
   - type: `html`
   - includes method summary and status/reason

Pass Criteria
- Required files exist and parse.
- `run_metadata.json` declares `status` and `reason`.
- If `status=ok`, `clean_raw.fif` is non-empty parsed raw with many channels and finite data.
- If `status=failed_precondition`, reason is explicit and failure artifacts remain parseable.

Expected Results
- Real computed preprocessing outputs when prerequisites are satisfied.
- Deterministic fail-fast artifacts when prerequisites are unmet.
