# Benchmark Mirror

This directory mirrors selected benchmark assets from the private working repository into a public-friendly layout.

## Scope

Phase A includes:

1. Code benchmark task folders from Harbor.
2. Selected Harbor JSON files.
3. A migration manifest and validation report.

## Layout

- `tasks/codebench/<TASK_ID>/`
- `harbor_json/neuroimage-code-bench.harbor.json`
- `harbor_json/neuroimage-theory-bench.harbor.json`
- `harbor_json/neuroimage-theory-rubric.harbor.json`
- `migration_manifest.codebench.json`
- `migration_logs/phase_a_validation.json`

## Source of Truth

- Harbor task source: `/home/zijiaochen/projects/brain_researcher_benchmark/harbor`
- Harbor JSON source: `/home/zijiaochen/projects/brain_researcher_benchmark/harbor_json`

## Notes

1. This phase copies task source files and excludes cache artifacts.
2. Terminal-Bench strict normalization (for example canary insertion and metadata harmonization) is intentionally deferred to a later pass.

## Contribute Benchmark Tasks

Use `benchmark/CONTRIBUTING_TASKS.md` for task authoring rules, validation commands, and PR checklist requirements for benchmark changes.
