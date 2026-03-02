Task: Calculate time-frequency representations for gamma band activity (ELEC-004)

Scope
- This task is an execution-focused code benchmark item.
- Dataset source: `Provided`.
- Dataset identifier: `mne_sample_dataset`.
- This task is dual-mode: real-compute when inputs exist, explicit fail-fast when prerequisites are missing.

Goal
- Resolve mounted inputs from `/task/cache/mne_sample_dataset` (or equivalent mounted input paths).
- Build epochs from auditory events and compute gamma-band (30-50 Hz) TFR.
- Export average TFR and a time-frequency plot.
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
1) `tfr_average.h5`
   - type: `file`
   - contains average TFR object

2) `time_frequency_plot.png`
   - type: `png`
   - min size: 300x300

Pass Criteria
- Required files exist and parse.
- `run_metadata.json` declares `status` and `reason`.
- If `status=ok`, TFR has non-zero frequency/time dimensions within gamma range.
- If `status=failed_precondition`, reason is explicit and artifacts remain valid.

Expected Results
- Real computed TFR outputs when prerequisites are satisfied.
- Deterministic fail-fast artifacts when prerequisites are unmet.
