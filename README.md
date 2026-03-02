# Brain Researcher

**Ask a neuro question. Get a reproducible result.**

[Visit Brain Researcher](https://brain-researcher.com) | [Issues](https://github.com/zjc062/brain-researcher-public/issues) | [Discussions](https://github.com/zjc062/brain-researcher-public/discussions)

Brain Researcher is an open-source neuroimaging AI agent for researchers and developers who want to move from research intent to auditable workflows.

Instead of relying on free-form code generation, Brain Researcher uses schema-constrained planning and a curated tool catalog to reduce execution errors and improve reproducibility.

## What It Does

- Helps users plan analyses in plain language.
- Grounds concepts and hypotheses using NeuroKG (task, region, disease, method relationships).
- Turns plans into explicit workflow node chains (DAG-style pipelines).
- Tracks parameters, tool versions, and run artifacts for review.
- Supports both Web UI workflows and IDE-based MCP workflows.

## How It Works (High Level)

1. Agent planning layer: a planner agent converts user intent into a workflow plan instead of writing free-form scripts.
2. Knowledge grounding layer: NeuroKG is queried to structure concepts (tasks, regions, diseases, methods) and support better hypothesis/planning decisions.
3. Workflow compiler layer: the agent selects from a curated tool catalog and builds a DAG-style node chain.
4. Contract validation layer: tool input/output schemas are checked before execution to reduce payload/parameter mismatches.
5. Execution layer: the same backend executes through Web Studio and MCP (Codex/Cursor/Claude Code) with traceable runs.

## Data Flow (Intent -> Run)

1. User provides intent, constraints, and dataset context.
2. Agent grounds key concepts with NeuroKG.
3. Agent compiles an executable node chain from validated tools.
4. Schema checks verify node-to-node compatibility.
5. Run executes and emits artifacts, logs, and parameters for audit/review.

## Current Status

As of March 2, 2026, Brain Researcher is in a hardening phase:

- Core surfaces are live (Studio, Library, Benchmark, NeuroKG, Hypothesis, MCP bridge).
- Main work is reliability, scientific rigor, and review quality.
- Current priorities are tracked in concrete issues below.

## Architecture At A Glance

### Web UI

- `Studio`: Intent -> Data -> Concepts -> Pipeline -> Verify.
- `Library`: official workflow catalog (node chains + defaults).
- `Tools` (Advanced): tool catalog and metadata auditing.
- `Datasets`: search/filter + Add to Plan.
- `Benchmark`: task definitions, criteria, governance review.
- `NeuroKG` (Advanced): node/edge/evidence exploration and multihop review.
- `Hypothesis`: staged ideation (`clarifying` -> `analysis/evidence ready` -> `completed`).

### MCP Agent Bridge

- Tool discovery and ranking in IDE agents (Codex/Cursor/Claude Code).
- Tool schema and payload contract checks.
- Execution reliability and traceability.
- Boundary safety for unsafe or hallucinated actions.

### Review Feedback Loop

1. Explore in UI or MCP.
2. Reproduce and capture IDs/logs.
3. Submit via issue forms.
4. Maintainers triage and ship fixes.

## 5-Minute Contributor Quickstart

1. Open [brain-researcher.com](https://brain-researcher.com).
2. Pick one review track from the table below.
3. Follow [REVIEW_PLAYBOOK.md](REVIEW_PLAYBOOK.md).
4. File one issue with exact IDs, expected vs actual behavior, and a concrete fix suggestion.

If credits block execution tests, top up in `Settings` at `https://brain-researcher.com/settings`.

## Priority Backlog

Source of truth is GitHub Issues.

| Priority | Theme | Concrete issues |
| --- | --- | --- |
| P0 | MCP runtime and privacy hardening | [#2](https://github.com/zjc062/brain-researcher-public/issues/2), [#5](https://github.com/zjc062/brain-researcher-public/issues/5) |
| P0 | Studio verify guardrails and validation | [#6](https://github.com/zjc062/brain-researcher-public/issues/6), [#7](https://github.com/zjc062/brain-researcher-public/issues/7), [#8](https://github.com/zjc062/brain-researcher-public/issues/8), [#9](https://github.com/zjc062/brain-researcher-public/issues/9) |
| P1 | NeuroKG query/curation/scoring quality | [#3](https://github.com/zjc062/brain-researcher-public/issues/3), [#4](https://github.com/zjc062/brain-researcher-public/issues/4), [#10](https://github.com/zjc062/brain-researcher-public/issues/10) |
| P1 | Open architecture decisions | [#11](https://github.com/zjc062/brain-researcher-public/issues/11), [#12](https://github.com/zjc062/brain-researcher-public/issues/12), [#13](https://github.com/zjc062/brain-researcher-public/issues/13), [#14](https://github.com/zjc062/brain-researcher-public/issues/14) |
| P1-P2 | Workflow, hypothesis, dataset, docs lanes | [Open issue forms](https://github.com/zjc062/brain-researcher-public/issues/new/choose) |

Benchmark-only backlog: [benchmark/TODO.md](benchmark/TODO.md)

## Review Tracks

| Review track | Where to click | Issue form |
| --- | --- | --- |
| Missing tool/workflow | Advanced -> Tools, then Library | [01-gap-tool-workflow](https://github.com/zjc062/brain-researcher-public/issues/new?template=01-gap-tool-workflow.yml) |
| Existing workflow defaults | Library -> Add to Plan -> Studio -> Review pipeline | [02-workflow-review](https://github.com/zjc062/brain-researcher-public/issues/new?template=02-workflow-review.yml) |
| Benchmark task rigor | [Benchmark](https://brain-researcher.com/benchmark) | [03-benchmark-review](https://github.com/zjc062/brain-researcher-public/issues/new?template=03-benchmark-review.yml) |
| KG definitions/edges | [NeuroKG](https://brain-researcher.com/neurokg) | [04-neurokg-edge-review](https://github.com/zjc062/brain-researcher-public/issues/new?template=04-neurokg-edge-review.yml) |
| Hypothesis quality | Hypothesis Explorer | [05-hypothesis-review](https://github.com/zjc062/brain-researcher-public/issues/new?template=05-hypothesis-review.yml) |
| MCP in IDE | Cursor / Claude Code / Codex with MCP | [06-mcp-integration](https://github.com/zjc062/brain-researcher-public/issues/new?template=06-mcp-integration.yml) |
| Studio blocked run | Studio -> Plan -> Verify | [07-studio-blocked](https://github.com/zjc062/brain-researcher-public/issues/new?template=07-studio-blocked.yml) |
| Studio -> MCP handoff | Configure in Studio, execute via MCP | [08-studio-mcp-handoff](https://github.com/zjc062/brain-researcher-public/issues/new?template=08-studio-mcp-handoff.yml) |
| Dataset coverage/metadata | Datasets explorer | [09-dataset-coverage](https://github.com/zjc062/brain-researcher-public/issues/new?template=09-dataset-coverage.yml) |
| Docs/demo reproducibility | Docs or demo trace | [10-docs-demo-repro](https://github.com/zjc062/brain-researcher-public/issues/new?template=10-docs-demo-repro.yml) |
| Open architecture question | Any architecture/product question | [11-open-question](https://github.com/zjc062/brain-researcher-public/issues/new?template=11-open-question.yml) |

## MCP Setup (Quick)

Use the maintainer-provided endpoint and token. Never commit credentials.

1. Export token:

```bash
export BR_MCP_TOKEN="<your_token>"
```

2. Configure one client:

Codex (prod MCP):

```bash
codex mcp add brain-researcher-prod \
  --url "https://brain-researcher.com/mcp" \
  --bearer-token-env-var BR_MCP_TOKEN
```

Cursor (`mcp.json` snippet):

```json
{
  "mcpServers": {
    "brain-researcher-prod": {
      "url": "https://brain-researcher.com/mcp",
      "headers": {
        "Authorization": "Bearer ${BR_MCP_TOKEN}",
        "Accept": "application/json, text/event-stream"
      }
    }
  }
}
```

Claude Code:

```bash
claude mcp add -s user --transport http brain-researcher-prod \
  https://brain-researcher.com/mcp \
  --header 'Authorization: Bearer ${BR_MCP_TOKEN}' \
  --header 'Accept: application/json, text/event-stream'
```

3. Smoke test prompt:
`Use brain-researcher-prod MCP and call server_info.`

### One-Click Self-Checks

Codex:

```bash
codex mcp list --json | python -c 'import json,sys; s={x["name"]:x for x in json.load(sys.stdin)}; ok=("brain-researcher-prod" in s and s["brain-researcher-prod"]["transport"].get("url")=="https://brain-researcher.com/mcp"); print("OK" if ok else "FAIL"); raise SystemExit(0 if ok else 1)'
```

Cursor:

```bash
TOKEN="${BR_MCP_TOKEN:?BR_MCP_TOKEN is not set}"; code=$(curl --max-time 8 -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${TOKEN}" -H 'Accept: application/json, text/event-stream' https://brain-researcher.com/mcp 2>/dev/null || true); [ "$code" = "200" ] && echo "OK (HTTP $code)" || (echo "FAIL (HTTP $code)"; exit 1)
```

Claude Code:

```bash
claude mcp list | rg -q 'brain-researcher-prod: .*\(HTTP\) - ✓ Connected' && echo "OK" || (echo "FAIL"; claude mcp list | sed -n '/brain-researcher-prod/p'; exit 1)
```

## Reviewer Rules

1. Default to read-only review behavior.
2. Do not click `Save governance` in Benchmark unless authorized.
3. Do not include PHI, secrets, or private credentials.
4. Include exact IDs whenever possible (workflow/tool/task/dataset/node/sessionId/runId).

## Contributing And Governance

- Contributor guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Reviewer playbook: [REVIEW_PLAYBOOK.md](REVIEW_PLAYBOOK.md)
- Benchmark task authoring: [benchmark/CONTRIBUTING_TASKS.md](benchmark/CONTRIBUTING_TASKS.md)
- Code of Conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- License: [LICENSE](LICENSE)
