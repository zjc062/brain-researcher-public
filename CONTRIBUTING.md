# Contributing to Brain Researcher

This guide is operational by design. Follow these steps directly when reviewing workflows, tools, benchmark tasks, KG reasoning, hypothesis generation, MCP integration, and studio execution behavior.

## 1) Universal Rules

1. Use a read-only review mindset.
Do not click Save governance unless you are an authorized maintainer.
2. Do not run expensive jobs unless needed for the specific report.
3. Do not submit PHI, secrets, credentials, or unauthorized data.
4. Always report exact context and IDs.

## 2) Required Report Payload (All Forms)

Every report should include:

1. Entry surface.
Library, Tools, Benchmark, NeuroKG, Hypothesis, Studio, Datasets, MCP.
2. How you searched/navigated.
Search terms, filter combinations, clicked path.
3. Exact IDs.
Workflow name, tool ID, benchmark task ID, node ID, dataset name, sessionId, runId.
4. Expected behavior vs actual behavior.
5. Suggested fix.
Concrete wording, parameter change, schema fix, or UI guidance change.

## 3) Label Taxonomy

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

## 4) Task Playbook

### 1. Add new tool/workflow gap

- Open form: [01-gap-tool-workflow.yml](.github/ISSUE_TEMPLATE/01-gap-tool-workflow.yml)
- Entry:
Tools (Advanced) or Library.
- Review:
Missing capability, duplicate tool, metadata gaps, unrealistic stage/cost.

### 2. Workflow review

- Open form: [02-workflow-review.yml](.github/ISSUE_TEMPLATE/02-workflow-review.yml)
- Entry:
Library -> Add to Plan -> Studio Plan/Verify.
- Review:
Node ordering, defaults (confounds/filter/atlas/HRF/threshold), blocked guidance quality.

### 3. Benchmark review

- Open form: [03-benchmark-review.yml](.github/ISSUE_TEMPLATE/03-benchmark-review.yml)
- Entry:
Benchmark board.
- Review:
Scope/Goal consistency, required outputs, pass criteria specificity, expected results realism.

### 4. NeuroKG edge/definition review

- Open form: [04-neurokg-edge-review.yml](.github/ISSUE_TEMPLATE/04-neurokg-edge-review.yml)
- Entry:
NeuroKG task/disease/ONVOC tabs.
- Review:
Missing definitions, overstated edges, weak evidence, multihop semantic quality.

### 5. Hypothesis explorer review

- Open form: [05-hypothesis-review.yml](.github/ISSUE_TEMPLATE/05-hypothesis-review.yml)
- Entry:
Hypothesis explorer stages.
- Review:
Novelty, factuality, bias, and whether evidence/plan/validation are truly ready.

### 6. MCP integration report

- Open form: [06-mcp-integration.yml](.github/ISSUE_TEMPLATE/06-mcp-integration.yml)
- Entry:
IDE (Cursor/Claude Code/Codex) MCP flow.
- Review:
Tool search quality, schema mismatch, payload mismatch, boundary safety.

### 7. Studio blocked report

- Open form: [07-studio-blocked.yml](.github/ISSUE_TEMPLATE/07-studio-blocked.yml)
- Entry:
Studio Plan -> Verify.
- Review:
Where unblock guidance is unclear or loops.

### 8. Studio <-> MCP handoff issue

- Open form: [08-studio-mcp-handoff.yml](.github/ISSUE_TEMPLATE/08-studio-mcp-handoff.yml)
- Entry:
Configure in Studio, execute in MCP.
- Review:
Missing fields/default mismatches/contract drift between UI and MCP execution.

### 9. Dataset coverage/metadata gap

- Open form: [09-dataset-coverage.yml](.github/ISSUE_TEMPLATE/09-dataset-coverage.yml)
- Entry:
Datasets explorer.
- Review:
Missing datasets, incomplete metadata, filter/search failure, Add to Plan errors.

### 10. Docs/demo reproducibility

- Open form: [10-docs-demo-repro.yml](.github/ISSUE_TEMPLATE/10-docs-demo-repro.yml)
- Entry:
Any public docs or demo trace.
- Review:
Zero-assumption reproducibility and exact break point.

### 11. Open question

- Open form: [11-open-question.yml](.github/ISSUE_TEMPLATE/11-open-question.yml)
- Entry:
Architecture or product direction questions.
- Review:
Question framing, current state, concrete proposal, tradeoffs, next steps.

## 5) Issues vs Discussions

1. Use Issues for actionable tracking items and structured reviews.
2. Use Discussions for open-ended community conversation.
3. For open questions that need decision tracking, use the Open question issue form.

## 6) Maintainer Triage Flow

1. Confirm `area/*` and `type/*` labels are present.
2. Move lifecycle manually through status labels.
3. Convert broad discussions into scoped follow-up issues when needed.

## 7) Governance and Safety Reminder

1. Unauthorized reviewers must not change benchmark governance fields.
2. Do not include private infrastructure details in screenshots/logs.
3. Redact sensitive payload sections before posting.

By participating, you agree to [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
