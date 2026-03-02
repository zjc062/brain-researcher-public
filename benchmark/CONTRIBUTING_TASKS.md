# Contributing Benchmark Tasks

This guide is for contributors adding or updating benchmark tasks in this repository.

## Scope

Use this guide when your PR touches:

- `benchmark/tasks/codebench/**`
- `benchmark/harbor_json/**`

For product review contributions (Studio, MCP, NeuroKG, etc.), use `REVIEW_PLAYBOOK.md`.

## Task Path Contract

Each task must live under:

- `benchmark/tasks/codebench/<TASK_ID>/`

Required files per task:

- `instruction.md`
- `task.toml`
- `environment/Dockerfile`
- `solution/solve.sh`
- `tests/test.sh`
- `tests/test_outputs.py`

## Recommended Workflow

1. Create a branch for the task.
2. Create or update one task folder under `benchmark/tasks/codebench/<TASK_ID>/`.
3. Keep instructions, solution, and tests consistent with each other.
4. Run local validation commands.
5. Open a PR and complete the benchmark checklist.

## Authoring Standards

### Instruction quality

- Use absolute paths in instructions.
- State expected outputs explicitly (file paths, format, schema, and acceptance conditions).
- Ensure every required behavior in `instruction.md` is verified by tests.

### Test quality

- Tests must verify all required outputs and acceptance criteria.
- Keep tests deterministic.
- Avoid hidden assumptions that are not documented in `instruction.md`.

### Reproducibility

- Pin Python package versions where needed for stable behavior.
- Do not pin apt package versions.
- Do not copy solution or tests into the runtime image unless intentionally required by the task design.

### Anti-cheat guardrails

- Do not leak answers in obvious filenames or static constants that bypass task intent.
- Do not allow tests to pass via unrelated file edits or shortcuts.
- Keep task data and expected outputs aligned with scientific intent.

## Validation Commands

Run these before opening a PR (adjust model/provider as needed):

```bash
# Oracle solvability check
harbor run -p benchmark/tasks/codebench/<TASK_ID> -a oracle

# Optional: model-based quality check
harbor tasks check benchmark/tasks/codebench/<TASK_ID> -m <provider/model>

# Optional: agent run sanity check
harbor run -p benchmark/tasks/codebench/<TASK_ID> -a <agent> -m <provider/model>
```

Expected outcome:

- Oracle run succeeds.
- Task checker reports no blocking issues.
- If an agent fails (for hard tasks), include failure analysis in PR notes.

## PR Requirements for Benchmark Changes

When touching benchmark paths, include in your PR body:

1. Task IDs changed.
2. Commands run and outcomes.
3. Why instruction/solution/tests are aligned.
4. Any known limits, assumptions, or follow-up work.

Use `.github/pull_request_template.md` and complete the benchmark checklist.
