# Contributing to Brain Researcher

This guide explains how external contributors can review Brain Researcher with minimal setup and clear reporting standards.

## Overall Aim

Brain Researcher aims to make neuroimaging analysis:

1. Conversational.
2. Rigorously scoped.
3. Reproducible by design.
4. Auditable in public.

## Scope of This Public Repo

This repository is the public collaboration hub for:

- Review workflows and issue templates.
- Benchmark task assets and migration artifacts.
- Quality hardening backlog and architecture discussions.

This repository is not a full mirror of private production internals.

## Current Status

Current phase: hardening (quality, reliability, and scientific rigor improvements across UI, MCP, KG, and benchmark surfaces).

## Start Here

1. Product/scientific review (Studio, MCP, NeuroKG, Hypothesis, datasets): use `REVIEW_PLAYBOOK.md`.
2. Benchmark task authoring (`benchmark/tasks/codebench/**`): use `benchmark/CONTRIBUTING_TASKS.md`.
3. If unsure: follow `REVIEW_PLAYBOOK.md`, submit one issue, and include IDs plus expected vs actual behavior.

## Document Ownership (Avoid Confusion)

Use each document for one purpose:

1. `README.md`: project overview, where to start, and links.
2. `REVIEW_PLAYBOOK.md`: click-by-click review procedures and issue routing (`tool` vs `workflow`).
3. `CONTRIBUTING.md` (this file): policy, labels, governance, and report quality standards.
4. `benchmark/CONTRIBUTING_TASKS.md`: benchmark task authoring and benchmark-specific rules.

## Universal Rules

1. Use read-only review behavior by default.
2. Do not click `Save governance` in Benchmark unless you are an authorized maintainer.
3. Avoid long or expensive runs unless needed for the report.
4. Do not submit PHI, secrets, private credentials, or unauthorized data.

## Unified Report Format (Use for every task)

Use this structure in every issue. All forms in `.github/ISSUE_TEMPLATE/` map to this format.

1. `Entry surface`: Library, Tools, Benchmark, NeuroKG, Hypothesis, Studio, Datasets, MCP.
2. `Page URL(s)`: exact page used.
3. `Search/filter path`: query terms, filters, and click path.
4. `IDs`: workflow/tool/task/dataset/node/sessionId/runId as applicable.
5. `Expected behavior`.
6. `Actual behavior`.
7. `Suggested fix`.
8. `Evidence`: screenshot, logs, payload snippets, or copied UI message.

## Label Taxonomy

### area labels

- `area/workflow`
- `area/tool`
- `area/benchmark`
- `area/neurokg`
- `area/hypothesis`
- `area/studio`
- `area/datasets`
- `area/docs`
- `area/mcp`
- `area/architecture`

### type labels

- `type/bug`
- `type/feature-request`
- `type/scientific-review`
- `type/discussion`

### status labels (maintainers apply manually)

- `status/imported`
- `status/triaged`
- `status/validated`
- `status/active`
- `status/deprecated`
- `status/archived`

## Task Playbook

Each task follows the same structure:

- `Entry`
- `How to review`
- `Review standards`
- `Report template fields`

### 1) Add new tool / new workflow gap

- Issue form: [01-gap-tool-workflow.yml](.github/ISSUE_TEMPLATE/01-gap-tool-workflow.yml)
- Entry:
Top nav -> `Advanced` -> `Tools` and top nav -> `Library`.
- How to review:
1. In `Tools`, use `Search tools...` with domain terms.
2. Open several tool cards and inspect metadata completeness.
3. In `Library`, use `Search workflows...` and inspect workflow coverage.
4. Check for missing workflows, duplicates, or naming inconsistency.
- Review standards:
1. Coverage: missing high-value tools/workflows are identified.
2. Consistency: naming/grouping is coherent.
3. Metadata quality: fields like domain/function/risk/stage/cost are populated and sensible.
- Report template fields:
1. Search terms used.
2. Missing or duplicate item name/ID.
3. Why this is a gap.
4. Suggested workflow placement, stage, and cost tier.

### 2) Tool/workflow review

- Issue form: [02-workflow-review.yml](.github/ISSUE_TEMPLATE/02-workflow-review.yml)
- Entry:
`Library` -> choose workflow -> `Add to Plan` -> `Studio` -> `Plan` -> `Review pipeline`.
- How to review:
1. Select one workflow and add it to Studio.
2. Choose analysis type in Pipeline.
3. Inspect Verify statuses (`Data validated`, `Workflow compatible`, `All inputs provided`, `Credits sufficient`).
4. Open `Review pipeline` and inspect node order and defaults.
- Review standards:
1. Node chain follows best practice order.
2. Defaults are defensible (confounds, filter, atlas, HRF, threshold).
3. Verify guidance is actionable when blocked.
- Report template fields:
1. Workflow name and pipeline name.
2. Node -> parameter -> current value -> suggested value.
3. Which Verify line blocked and why.
4. Concrete UI or default-fix suggestion.

### 3) Benchmark review

- Issue form: [03-benchmark-review.yml](.github/ISSUE_TEMPLATE/03-benchmark-review.yml)
- Entry:
[Benchmark board](https://brain-researcher.com/benchmark).
- How to review:
1. Select dataset (for example NeuroimageCodeBench).
2. Search task by ID or keyword.
3. Open task detail and inspect Scope, Goal, Input Requirements, Required Outputs, Pass Criteria, Expected Results.
4. Do not click `Save governance`.
- Review standards:
1. Scope and Goal are aligned.
2. Required Outputs are specific and testable.
3. Pass Criteria are measurable and unambiguous.
4. Expected Results are scientifically realistic.
- Report template fields:
1. Dataset and task ID.
2. Problematic section(s).
3. Why current wording is weak.
4. Proposed replacement wording or validation logic.

### 4) Validate KG edge and definition quality

- Issue form: [04-neurokg-edge-review.yml](.github/ISSUE_TEMPLATE/04-neurokg-edge-review.yml)
- Entry:
[NeuroKG](https://brain-researcher.com/neurokg).
- How to review:
1. Search known node in Task, Disease, or ONVOC tabs.
2. Inspect Overview definition and connections.
3. Toggle `Show unverified evidence` depending on review goal.
4. Run `Run multihop reasoning` and inspect path semantics.
5. Check `Open deep-research prompt` for framing quality.
- Review standards:
1. Definitions are present and precise.
2. Edges avoid overclaiming causality from correlation.
3. Multihop chains are semantically coherent.
4. Claims use appropriately strong evidence.
- Report template fields:
1. Node name and node ID.
2. Edge/path under review.
3. Expected edge semantics.
4. Suggested qualifiers (species, population, modality) or relation type change.

### 5) Hypothesis generator review

- Issue form: [05-hypothesis-review.yml](.github/ISSUE_TEMPLATE/05-hypothesis-review.yml)
- Entry:
`Hypothesis` page, including your sample runs:
- `https://brain-researcher.com/hypothesis?sessionId=session-mm88g4ch-9ojsx0&runId=hrun-mm88h8nq-weo6jx`
- `https://brain-researcher.com/hypothesis?sessionId=session-mm87c8o8-x27ht9&runId=hrun-mm87ciol-cp3r9x`
- How to review:
1. Identify stage (`clarifying`, `analysis ready`, `evidence ready`, `completed`).
2. Inspect Research Canvas consistency.
3. Inspect Candidates, Evidence, Plan, and Validation sections.
4. Check whether claims are novel, factual, and unbiased.
- Review standards:
1. Novelty is real, not simple rephrasing.
2. Evidence supports conclusions.
3. No obvious factual hallucination.
4. Plan includes confound control, leakage control, and reproducibility logic.
5. Formatting and readability are usable.
- Report template fields:
1. `sessionId` and `runId`.
2. Stage observed.
3. Module reviewed (Canvas/Evidence/Plan/Validation).
4. Issue type (novelty/factual/bias/format).
5. Proposed correction.

### 6) MCP integration review

- Issue form: [06-mcp-integration.yml](.github/ISSUE_TEMPLATE/06-mcp-integration.yml)
- Entry:
Cursor, Claude Code, or Codex with Brain Researcher MCP configured.
- How to review:
1. Prompt tool discovery (`use brain_researcher_mcp to ...`).
2. Check schema comprehension and parameter fill quality.
3. Execute tools and inspect payload/contract errors.
4. Run boundary checks for unsafe path or shell behavior.
- Review standards:
1. Tool retrieval is relevant.
2. Schema and payload match.
3. Execution is reliable.
4. Safety boundaries are enforced.
- Report template fields:
1. IDE and exact prompt.
2. Failure mode (search/schema/execution/boundary).
3. Error logs or payload excerpt.
4. Suggested retrieval/schema/safety fix.

### 7) Studio run analysis blocked review

- Issue form: [07-studio-blocked.yml](.github/ISSUE_TEMPLATE/07-studio-blocked.yml)
- Entry:
`Studio` -> `Plan` -> `Verify`.
- How to review:
1. Start New Chat in Studio.
2. Set Intent and try Data/Concepts/Pipeline.
3. Observe which Verify item is blocked.
4. Use `Review pipeline` and optionally `Ask Agent to fix`.
- Review standards:
1. Block reason is understandable.
2. Unblock path is explicit.
3. Error copy is precise and actionable.
- Report template fields:
1. Pipeline/workflow name.
2. Blocked Verify item.
3. Exact steps and message text.
4. UX improvement proposal.

### 8) Studio + MCP handoff review

- Issue form: [08-studio-mcp-handoff.yml](.github/ISSUE_TEMPLATE/08-studio-mcp-handoff.yml)
- Entry:
Build plan in Studio, then execute through MCP in IDE.
- How to review:
1. Configure Data/Concepts/Pipeline in Studio.
2. Trigger equivalent run through MCP.
3. Compare expected contract and actual payload requirements.
- Review standards:
1. Studio state is transferable.
2. Defaults are consistent between UI and MCP.
3. No hidden required parameter mismatch.
- Report template fields:
1. Studio state snapshot.
2. MCP prompt used.
3. Expected handoff behavior.
4. Actual mismatch and suggested contract fix.

### 9) Dataset coverage and metadata review

- Issue form: [09-dataset-coverage.yml](.github/ISSUE_TEMPLATE/09-dataset-coverage.yml)
- Entry:
`Datasets` explorer.
- How to review:
1. Search by dataset name/portal/keyword.
2. Apply filters.
3. Inspect dataset card metadata.
4. Test `View dataset` and `Add to Plan`.
- Review standards:
1. Coverage includes expected datasets.
2. Metadata is complete and accurate.
3. Search/filter behavior has good recall.
4. Add to Plan works reliably.
- Report template fields:
1. Portal/filter combo.
2. Dataset name.
3. Problem type.
4. Expected vs actual result.
5. Metadata or pipeline integration fix.

### 10) Documentation/demo reproducibility review

- Issue form: [10-docs-demo-repro.yml](.github/ISSUE_TEMPLATE/10-docs-demo-repro.yml)
- Entry:
Any official doc page or demo trace.
- How to review:
1. Follow instructions from zero assumptions.
2. Stop exactly when blocked.
3. Record the first failing step and message.
- Review standards:
1. A new user can complete documented steps.
2. Prerequisites are explicit.
3. Error handling guidance exists.
- Report template fields:
1. Doc/demo page name.
2. Steps followed.
3. Expected output.
4. Actual break point.
5. Proposed documentation patch.

### 11) Open question

- Issue form: [11-open-question.yml](.github/ISSUE_TEMPLATE/11-open-question.yml)
- Entry:
Use for architecture/product questions that need tracked decision-making.
- How to review:
1. Define the decision question.
2. Document current state.
3. Propose one concrete direction.
4. State tradeoffs and next steps.
- Review standards:
1. Problem is clearly scoped.
2. Proposal is actionable.
3. Risks and migration cost are explicit.
- Report template fields:
1. Area label.
2. Open question statement.
3. Current state summary.
4. Proposed direction.
5. Tradeoffs and next steps.

## Issues vs Discussions

1. Use Issues for all structured review tasks and tracked open questions.
2. Use Discussions for broad conversation and community Q&A.

## Maintainer Triage Flow

1. Confirm `area/*` and `type/*` labels.
2. Apply lifecycle label manually (`status/*`).
3. Convert broad threads into scoped execution issues when needed.

By participating, you agree to [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
