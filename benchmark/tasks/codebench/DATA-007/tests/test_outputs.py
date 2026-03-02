import json
import os
import re
from pathlib import Path

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/app/output"))
REQUIRED_OUTPUTS = ["train_subjects.txt", "val_subjects.txt", "test_subjects.txt"]
OUTPUT_SCHEMA = {
    "train_subjects.txt": {"type": "text"},
    "val_subjects.txt": {"type": "text"},
    "test_subjects.txt": {"type": "text"},
}
METRIC_VALIDATION = {}


def _read_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _target_counts(n: int) -> tuple[int, int, int]:
    raw = [0.8 * n, 0.1 * n, 0.1 * n]
    base = [int(x) for x in raw]
    remaining = n - sum(base)
    remainders = [(raw[i] - base[i], -i, i) for i in range(3)]
    remainders.sort(reverse=True)
    for _, _, idx in remainders[:remaining]:
        base[idx] += 1
    return base[0], base[1], base[2]


def test_required_outputs_exist():
    for name in REQUIRED_OUTPUTS:
        path = OUTPUT_DIR / name
        assert path.exists(), f"Missing required output: {path}"
        assert path.is_file(), f"Required output is not a file: {path}"


def test_run_metadata_basic_contract():
    meta_path = OUTPUT_DIR / "run_metadata.json"
    assert meta_path.exists(), "run_metadata.json is required"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    required_keys = [
        "task_id",
        "dataset_source",
        "dataset_id",
        "status",
        "reason",
        "seed",
        "n_subjects_total",
        "n_train",
        "n_val",
        "n_test",
    ]
    for key in required_keys:
        assert key in meta, f"Missing run_metadata key: {key}"

    assert meta["task_id"] == "DATA-007"
    assert meta["dataset_source"] == "OpenNeuro"
    assert meta["dataset_id"] == "ds000030"
    assert meta["seed"] == 42
    assert meta["status"] in {"ok", "failed_precondition"}
    assert isinstance(meta["reason"], str) and meta["reason"].strip()
    assert int(meta["n_subjects_total"]) >= 0
    assert int(meta["n_train"]) >= 0
    assert int(meta["n_val"]) >= 0
    assert int(meta["n_test"]) >= 0


def test_split_semantics_match_status():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    train_lines = _read_lines(OUTPUT_DIR / "train_subjects.txt")
    val_lines = _read_lines(OUTPUT_DIR / "val_subjects.txt")
    test_lines = _read_lines(OUTPUT_DIR / "test_subjects.txt")

    status = meta["status"]
    reason = meta["reason"]

    if status == "ok":
        train = [x for x in train_lines if x.startswith("sub-")]
        val = [x for x in val_lines if x.startswith("sub-")]
        test = [x for x in test_lines if x.startswith("sub-")]

        assert train and val and test, "All splits must be non-empty when status=ok"
        assert all("FAILED_PRECONDITION" not in x.upper() for x in train_lines + val_lines + test_lines)

        train_set, val_set, test_set = set(train), set(val), set(test)
        assert not (train_set & val_set), "train and val overlap"
        assert not (train_set & test_set), "train and test overlap"
        assert not (val_set & test_set), "val and test overlap"

        merged = train_set | val_set | test_set
        assert len(merged) == int(meta["n_subjects_total"])
        assert len(train) == int(meta["n_train"])
        assert len(val) == int(meta["n_val"])
        assert len(test) == int(meta["n_test"])

        n_total = int(meta["n_subjects_total"])
        expected = _target_counts(n_total)
        tol = max(2, int(round(0.05 * n_total)))
        assert abs(len(train) - expected[0]) <= tol
        assert abs(len(val) - expected[1]) <= tol
        assert abs(len(test) - expected[2]) <= tol

        used = meta.get("used_subject_ids") or []
        assert set(used) == merged

        pattern = re.compile(r"^sub-[A-Za-z0-9][A-Za-z0-9_-]*$")
        assert all(pattern.match(sid) for sid in merged)
    else:
        for lines in [train_lines, val_lines, test_lines]:
            assert any("FAILED_PRECONDITION" in x.upper() for x in lines), (
                "Each split file must explicitly state fail-fast status"
            )
            assert any(f"reason={reason}" == x for x in lines), "Fail-fast reason must be explicit and consistent"
            assert not any(x.startswith("sub-") for x in lines), "No subject IDs allowed when fail-fast"

        assert int(meta["n_train"]) == 0
        assert int(meta["n_val"]) == 0
        assert int(meta["n_test"]) == 0


def test_traceability_fields_non_empty_when_available():
    meta = json.loads((OUTPUT_DIR / "run_metadata.json").read_text(encoding="utf-8"))
    assert "snapshot_tag" in meta
    assert "participants_row_count" in meta
    assert "subject_dir_count" in meta
    assert int(meta["participants_row_count"]) >= 0
    assert int(meta["subject_dir_count"]) >= 0
