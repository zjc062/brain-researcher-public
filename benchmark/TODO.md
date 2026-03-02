# Benchmark TODO Backlog

This file is the benchmark-specific backlog view.

Authoritative source of truth is GitHub Issues.

- Open/update a benchmark issue first.
- Then add or update the issue link in this table.
- Use labels: `area/benchmark` + one `type/*` + optional `status/*`.

| Priority | TODO | Issue |
| --- | --- | --- |
| P0 | Improve scientifically weak or ambiguous pass criteria in benchmark tasks | [Open benchmark scientific-review issues](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fbenchmark+label%3Atype%2Fscientific-review) |
| P0 | Normalize benchmark task contracts (`instruction`, expected outputs, tests alignment) | [Open benchmark issues](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fbenchmark) |
| P1 | Fill metadata gaps and consistency issues in imported benchmark tasks | [Open benchmark feature-request issues](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fbenchmark+label%3Atype%2Ffeature-request) |
| P1 | Add maintainer QA sweep for newly imported task batches before release | [Open benchmark triage queue](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fbenchmark+-label%3Astatus%2Farchived) |
| P2 | Introduce lightweight benchmark validation CI checks (deferred item) | [Open benchmark bug/issues queue](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fbenchmark+label%3Atype%2Fbug) |

## How Maintainers Use This

1. Keep this table short and priority-first.
2. Every row must point to a live issue query or issue number.
3. When a row is done, remove it and keep history in closed issues.
