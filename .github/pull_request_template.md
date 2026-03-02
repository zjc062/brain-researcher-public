## Summary

Describe what changed and why.

## Linked issue

Reference the related issue, for example `Closes #123`.

## Validation

Describe how this was validated.

## General Checklist

- [ ] Scope is focused and does not include unrelated changes.
- [ ] No secrets, PHI, or private credentials are included.
- [ ] Documentation is updated if behavior changed.
- [ ] Test or verification evidence is included.

## Benchmark Task Checklist

Complete this section if your PR touches `benchmark/tasks/**` or `benchmark/harbor_json/**`.

- [ ] I listed all changed task IDs below.
- [ ] I ran `harbor run -p benchmark/tasks/codebench/<TASK_ID> -a oracle` for each changed task.
- [ ] I ran `harbor tasks check benchmark/tasks/codebench/<TASK_ID> -m <provider/model>` or documented why not.
- [ ] Task instruction, tests, and solution are aligned (no behavior mismatch).
- [ ] Output files and schemas expected by tests are explicitly documented in `instruction.md` or `task.toml`.
- [ ] Docker/task setup is reproducible (Python deps pinned where needed, apt versions not pinned).
- [ ] I reviewed anti-cheat risks and documented how this task avoids trivial leakage.

### Changed task IDs

List each changed task ID (for example `CLIN-005`, `CONN-012`).

### Benchmark validation log

Paste exact commands and concise outcomes for each task.

### Anti-cheat and risk notes

Briefly explain known bypass risks, limitations, or follow-up work.
