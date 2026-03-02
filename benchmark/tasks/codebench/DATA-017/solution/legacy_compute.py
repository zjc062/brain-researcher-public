import json
import os
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "DATA-017"
DATASET_ID = "custom_missing_modalities"
REQUIRED_INPUTS = ["anat_t1w", "func_bold", "dwi", "events_tsv"]


def candidate_roots() -> list[Path]:
    out: list[Path] = []
    seen = set()

    env_input = os.environ.get("INPUT_DIR")
    if env_input:
        out.append(Path(env_input))
        out.append(Path(env_input) / DATASET_ID)
    env_root = os.environ.get("PROVIDED_INPUTS_ROOT")
    if env_root:
        out.append(Path(env_root) / DATASET_ID)

    out.extend(
        [
            Path("/task/cache") / DATASET_ID,
            Path("/task/cache"),
            Path("/task/input") / DATASET_ID,
            Path("/task/input"),
            Path("/task/input/provided_inputs") / DATASET_ID,
            Path("/app/input") / DATASET_ID,
            Path("/app/input"),
            Path("/home/zijiaochen/projects/brain_researcher_benchmark/provided_inputs") / DATASET_ID,
        ]
    )

    dedup = []
    for path in out:
        key = str(path)
        if key not in seen:
            seen.add(key)
            dedup.append(path)
    return dedup


def detect_modalities(files: list[Path]) -> dict:
    found = {k: [] for k in REQUIRED_INPUTS}
    for file_path in files:
        p = str(file_path).lower()
        if ("t1w" in p) and (p.endswith(".nii") or p.endswith(".nii.gz")):
            found["anat_t1w"].append(str(file_path))
        if ("bold" in p) and (p.endswith(".nii") or p.endswith(".nii.gz")):
            found["func_bold"].append(str(file_path))
        if ("dwi" in p) and (p.endswith(".nii") or p.endswith(".nii.gz")):
            found["dwi"].append(str(file_path))
        if p.endswith("events.tsv"):
            found["events_tsv"].append(str(file_path))
    return found


def pick_best_existing_root(paths: list[Path]):
    existing = [p for p in paths if p.exists() and p.is_dir()]
    if not existing:
        return None, []

    best_root = None
    best_files = []
    for root in existing:
        files = [p for p in root.rglob("*") if p.is_file()]
        if len(files) > len(best_files):
            best_root = root
            best_files = files
    return best_root, best_files


def main() -> None:
    output_dir = Path(os.environ.get("OUTPUT_DIR", "/app/output")).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    checked_paths = [str(p) for p in candidate_roots()]
    root, files = pick_best_existing_root([Path(p) for p in checked_paths])

    present_inputs = {key: [] for key in REQUIRED_INPUTS}
    missing_inputs = list(REQUIRED_INPUTS)

    if root is not None:
        present_inputs = detect_modalities(files)
        missing_inputs = [key for key in REQUIRED_INPUTS if not present_inputs[key]]

    if root is None:
        status = "failed_precondition"
        reason = "missing_input_root"
    elif missing_inputs:
        status = "failed_precondition"
        reason = "missing_required_modalities"
    else:
        status = "ok"
        reason = "all_required_inputs_present"

    payload = {
        "status": status,
        "reason": reason,
        "task_id": TASK_ID,
        "dataset_source": "Provided",
        "dataset_id": DATASET_ID,
        "required_inputs": REQUIRED_INPUTS,
        "missing_inputs": missing_inputs,
        "missing_inputs_count": len(missing_inputs),
        "checked_paths": checked_paths,
        "data_root": str(root) if root else "",
        "n_scanned_files": len(files),
        "present_inputs": {k: len(v) for k, v in present_inputs.items()},
        "present_examples": {k: (v[0] if v else "") for k, v in present_inputs.items()},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    (output_dir / "preflight_check.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    reason_text = (
        f"status={status}\n"
        f"reason={reason}\n"
        f"missing_inputs={','.join(missing_inputs)}\n"
        f"data_root={payload['data_root']}\n"
    )
    if status == "failed_precondition":
        reason_text = "FAILED_PRECONDITION\n" + reason_text
    (output_dir / "fail_fast_reason.txt").write_text(reason_text, encoding="utf-8")

    run_meta = {
        "task_id": TASK_ID,
        "dataset_source": "Provided",
        "dataset_id": DATASET_ID,
        "status": status,
        "reason": reason,
        "missing_inputs_count": len(missing_inputs),
        "n_scanned_files": len(files),
        "checked_paths": checked_paths,
        "data_root": payload["data_root"],
        "required_inputs": REQUIRED_INPUTS,
        "missing_inputs": missing_inputs,
        "generated_at": payload["generated_at"],
    }
    (output_dir / "run_metadata.json").write_text(json.dumps(run_meta, indent=2), encoding="utf-8")
    print(f"status={status} reason={reason} missing={len(missing_inputs)}")


if __name__ == "__main__":
    main()
