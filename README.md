# Brain Researcher

**Ask a neuro question. Get a reproducible result.**

[Visit Brain Researcher](https://brain-researcher.com) | [Report an Issue](https://github.com/zjc062/brain-researcher-public/issues) | [Join Discussions](https://github.com/zjc062/brain-researcher-public/discussions)

Brain Researcher is an open neuroimaging assistant that turns conversational intent into reproducible workflows, with a dual interface:

1. Web UI for planning, library browsing, benchmark review, knowledge graph exploration, and hypothesis generation.
2. MCP integration for triggering the same workflows in IDE agent environments (Cursor, Claude Code, Codex) with strict schema and execution boundaries.

## Project Goal

We want neuroimaging analysis to be:

1. Conversational.
Users describe goals, constraints, and data at a high level.
2. Rigorously scoped.
Tasks encode what good science means: inputs, outputs, and pass criteria.
3. Reproducible by design.
Workflows are explicit node chains with parameters and provenance-friendly outputs.
4. Auditable.
Public benchmark and KG surfaces allow transparent community review.

## Current Architecture

### 1) Web UI

- Studio: Intent -> Data -> Concepts -> Pipeline -> Verify, plus Results/Steps views.
- Library: official workflows as explicit node chains.
- Tools (advanced): tool catalog metadata and auditing surface.
- Datasets: dataset explorer and Add to Plan flow.
- Benchmark: task, dataset, and governance surface.
- NeuroKG (advanced): node/edge/evidence exploration, multihop reasoning.
- Hypothesis: staged hypothesis exploration and validation artifacts.

### 2) MCP Integration

- Tool discovery and ranking.
- Tool schema and payload contract correctness.
- Execution reliability.
- Boundary safety against unsafe file/path/shell behavior.

## Current Stage

We are in a hardening phase.

1. Workflow defaults and node ordering need best-practice review.
2. Benchmark tasks need tighter wording and pass criteria specificity.
3. KG definitions and edges need quality cleanup.
4. MCP integration needs robustness and safety validation.

## Where Community Can Help

| Task | Open Form |
| --- | --- |
| Add missing tool/workflow gaps | [Gap request](https://github.com/zjc062/brain-researcher-public/issues/new?template=01-gap-tool-workflow.yml) |
| Review workflow defaults and node order | [Workflow review](https://github.com/zjc062/brain-researcher-public/issues/new?template=02-workflow-review.yml) |
| Review benchmark task quality | [Benchmark review](https://github.com/zjc062/brain-researcher-public/issues/new?template=03-benchmark-review.yml) |
| Validate NeuroKG definitions and edges | [NeuroKG review](https://github.com/zjc062/brain-researcher-public/issues/new?template=04-neurokg-edge-review.yml) |
| Audit Hypothesis Explorer outputs | [Hypothesis review](https://github.com/zjc062/brain-researcher-public/issues/new?template=05-hypothesis-review.yml) |
| Report MCP integration issues | [MCP report](https://github.com/zjc062/brain-researcher-public/issues/new?template=06-mcp-integration.yml) |
| Report Studio blocked flows | [Studio blocked](https://github.com/zjc062/brain-researcher-public/issues/new?template=07-studio-blocked.yml) |
| Report Studio <-> MCP handoff mismatch | [Handoff issue](https://github.com/zjc062/brain-researcher-public/issues/new?template=08-studio-mcp-handoff.yml) |
| Report dataset coverage/metadata gaps | [Dataset gap](https://github.com/zjc062/brain-researcher-public/issues/new?template=09-dataset-coverage.yml) |
| Reproduce docs/demo trace failures | [Docs repro](https://github.com/zjc062/brain-researcher-public/issues/new?template=10-docs-demo-repro.yml) |
| Raise open architecture/product questions | [Open question](https://github.com/zjc062/brain-researcher-public/issues/new?template=11-open-question.yml) |

## Important Reviewer Rules

1. Do not edit benchmark governance unless you are an authorized maintainer.
2. Treat advanced Tools and NeuroKG views as auditing surfaces.
3. Do not submit PHI, secrets, or private credentials.
4. Report exact IDs whenever possible: workflow, tool, task, dataset, node, sessionId, runId.

## Contributing and Governance

- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of Conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- License: [LICENSE](LICENSE)
