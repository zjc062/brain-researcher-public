# Contributing to Brain Researcher

Thanks for helping improve Brain Researcher. We are currently focused on scientific and platform validation. You can contribute high-impact feedback without writing code.

## Scope of contributions in this phase

1. Scientific and pipeline review.
2. Platform robustness and UX review.
3. Documentation clarity and correctness.

## High-impact review areas

### Scientific and pipeline review

1. Workflow defaults.
Check whether defaults such as smoothing, confounds, and preprocessing choices align with current best practices.
2. Benchmark tasks.
Check whether pass criteria are specific, measurable, and scientifically defensible.
3. NeuroKG quality.
Report missing definitions, overstated edges, weak evidence links, and flawed multi-hop reasoning.
4. Hypothesis auditing.
Flag factual errors, hallucinations, unjustified claims, and model bias.

### Platform and technical testing

1. Missing tools or datasets.
Tell us what key capabilities are absent from the catalog.
2. Studio roadblocks.
Report where planning or verification flow blocks progress.
3. MCP robustness.
Report tool execution failures, payload mismatches, and unsafe boundary attempts.

## How to submit useful issues

Use the issue templates:

- Bug report: execution failures, mismatches, broken behaviors.
- Feature request: missing capability, improvement proposal.
- Documentation issue: unclear or incorrect docs.

Every strong report should include:

1. Exact identifiers where applicable.
`workflow_name`, `task_id`, `tool_id`, `node_id`, `run_id`, dataset identifier.
2. Expected behavior.
3. Actual behavior.
4. Reproduction steps.
5. Evidence artifacts.
Error message, stack trace, screenshots, logs, payload snippet.
6. Concrete suggestion.

## Discussions vs Issues

- Use Issues for actionable work items.
- Use Discussions for open-ended questions, ideas, and community conversation.
- Maintainers may convert actionable Discussions into Issues for tracking.

## Reviewer safety and governance rules

1. Do not change benchmark governance unless explicitly authorized.
2. Use a read-only mindset for advanced Tools and NeuroKG auditing surfaces.
3. Never include PHI, credentials, or private infrastructure details.
4. Only test datasets you are authorized to access and process.

## Documentation contributions

For docs changes, include:

1. The exact page or file path.
2. The current problematic text.
3. The proposed replacement text.
4. The expected user impact.

## Pull requests

Code PRs are accepted, but this phase prioritizes test and review feedback. If you submit a PR:

1. Link the related Issue.
2. Keep scope small and focused.
3. Add validation notes and test evidence.
4. Confirm no secrets or sensitive data are included.
5. Update docs when behavior changes.

## Code of Conduct

By participating, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

