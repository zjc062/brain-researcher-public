# Brain Researcher

**Ask a neuro question. Get a reproducible result.**

[Visit Brain Researcher](https://brain-researcher.com) | [Report an Issue](https://github.com/zjc062/brain-researcher-public/issues) | [Join Discussions](https://github.com/zjc062/brain-researcher-public/discussions)

Brain Researcher is an open-source neuroimaging AI agent. It bridges high-level research intent and rigorous execution by turning natural language requests into structured, reproducible workflows.

## Our technical approach

1. **Schema-constrained planning**
The agent composes pipelines from predefined tools and contract-bound inputs and outputs instead of free-form scripts.
2. **Knowledge-grounded reasoning**
Reasoning is grounded in NeuroKG, an evidence-driven graph that connects brain regions, tasks, and diseases to scientific literature.
3. **MCP agent bridge**
The tool catalog and orchestration engine are exposed via MCP so IDE agents can execute safely with boundary controls.

## Current phase

We are in a testing and refinement phase. Domain reviewers can contribute without writing code by auditing scientific defaults, benchmark rigor, and execution behavior.

## Where to post

| You have this kind of feedback | Post here |
| --- | --- |
| Reproducible bug, execution failure, payload mismatch | [Bug report](https://github.com/zjc062/brain-researcher-public/issues/new?template=bug_report.yml) |
| New capability request, missing tool or dataset, workflow improvement | [Feature request](https://github.com/zjc062/brain-researcher-public/issues/new?template=feature_request.yml) |
| Missing, incorrect, or unclear docs | [Documentation issue](https://github.com/zjc062/brain-researcher-public/issues/new?template=docs.yml) |
| Open-ended questions, brainstorming, community discussion | [Discussions](https://github.com/zjc062/brain-researcher-public/discussions) |

## Important reviewer rules

1. Do not edit benchmark governance unless you are an authorized maintainer.
2. Treat advanced Tools and NeuroKG views as audit surfaces.
3. Never submit PHI or data you do not have rights to process.
4. Include exact IDs when possible: workflow name, task ID, tool ID, node ID, run ID.

## Contributing and governance

- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of Conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- License: [LICENSE](LICENSE)
