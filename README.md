# Brain Researcher

**Ask a neuro question. Get a reproducible result.**

[Visit Brain Researcher](https://brain-researcher.com) | [Report an Issue](https://github.com/zjc062/brain-researcher-public/issues) | [Join Discussions](https://github.com/zjc062/brain-researcher-public/discussions)

Brain Researcher is an open neuroimaging assistant that turns conversational intent into reproducible workflows.

## Project Goal

We want neuroimaging analysis to be:

1. Conversational.
2. Rigorously scoped.
3. Reproducible by design.
4. Auditable in public.

## Current Architecture

### Web UI

- Studio: Intent -> Data -> Concepts -> Pipeline -> Verify.
- Library: official workflow catalog.
- Tools (Advanced): tool catalog and metadata auditing.
- Datasets: search/filter and Add to Plan.
- Benchmark: task instructions and governance surface.
- NeuroKG (Advanced): node/edge/evidence and multihop review.
- Hypothesis: staged ideation and validation artifacts.

### MCP integration

- Tool discovery and ranking.
- Schema/payload contract checks.
- Execution reliability.
- Boundary safety.

## Current Stage

We are in a hardening phase and need reviewer feedback across methods, UX, KG quality, and MCP reliability.

## Contribution Lanes

1. Product and scientific review lane: use [REVIEW_PLAYBOOK.md](REVIEW_PLAYBOOK.md) and submit via issue forms.
2. Benchmark task authoring lane: use [benchmark/CONTRIBUTING_TASKS.md](benchmark/CONTRIBUTING_TASKS.md) for `benchmark/tasks/codebench/**` changes.

## MCP Setup (Quick)

Use maintainer-provided MCP endpoint and token. Do not commit credentials.

1. Export token locally:

```bash
export BR_MCP_TOKEN="<your_token>"
```

2. Use one of the client setups below.

### Codex CLI

Option A: local stdio server

```bash
codex mcp add brain-researcher -- brain-researcher-mcp
```

Option B: production HTTP MCP server

```bash
codex mcp add brain-researcher-prod \
  --url "https://brain-researcher.com/mcp" \
  --bearer-token-env-var BR_MCP_TOKEN
```

Check:

```bash
codex mcp list --json
```

Note: current Codex stores MCP servers in `~/.codex/config.toml`.

### Cursor

Open Cursor MCP settings and add an HTTP server named `brain-researcher-prod` with:

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

### Claude Code

Register directly with CLI:

```bash
claude mcp add -s user --transport http brain-researcher-prod \
  https://brain-researcher.com/mcp \
  --header 'Authorization: Bearer ${BR_MCP_TOKEN}' \
  --header 'Accept: application/json, text/event-stream'
```

3. Reload MCP connectors in your client.
4. Smoke test prompt:
`Use brain-researcher-prod MCP and call server_info.`

### One-Click Self-Checks (Prod MCP)

Codex (server registered with correct prod URL):

```bash
codex mcp list --json | python -c 'import json,sys; s={x["name"]:x for x in json.load(sys.stdin)}; ok=("brain-researcher-prod" in s and s["brain-researcher-prod"]["transport"].get("url")=="https://brain-researcher.com/mcp"); print("OK" if ok else "FAIL"); raise SystemExit(0 if ok else 1)'
```

Cursor (token + prod endpoint preflight used by Cursor HTTP MCP):

```bash
TOKEN="${BR_MCP_TOKEN:?BR_MCP_TOKEN is not set}"; code=$(curl --max-time 8 -sS -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${TOKEN}" -H 'Accept: application/json, text/event-stream' https://brain-researcher.com/mcp 2>/dev/null || true); [ "$code" = "200" ] && echo "OK (HTTP $code)" || (echo "FAIL (HTTP $code)"; exit 1)
```

Claude Code (server connected to prod MCP):

```bash
claude mcp list | rg -q 'brain-researcher-prod: .*\(HTTP\) - ✓ Connected' && echo "OK" || (echo "FAIL"; claude mcp list | sed -n '/brain-researcher-prod/p'; exit 1)
```

## 5-Minute Contributor Quickstart

1. Open [brain-researcher.com](https://brain-researcher.com).
2. Pick one review track from the table below.
3. Follow the click path in [REVIEW_PLAYBOOK.md](REVIEW_PLAYBOOK.md) (or [CONTRIBUTING.md](CONTRIBUTING.md)).
4. Submit one issue using the linked form.
5. Include IDs, expected vs actual behavior, and a concrete fix suggestion.

If credits block execution tests, you can top up in `Settings` at `https://brain-researcher.com/settings`.

## TODO Dashboard

Authoritative source of truth is GitHub Issues (assignable, triageable, closable).

- Global TODO overview: this section.
- Benchmark-specific backlog: [benchmark/TODO.md](benchmark/TODO.md).
- Rule: open/update issue first, then add the issue link here.

| Priority | Area | TODO | Issue |
| --- | --- | --- | --- |
| P0 | `area/mcp` | Stabilize tool search/schema/execution + safety boundary regressions | [Open MCP issues](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fmcp) |
| P0 | `area/studio` | Reduce Verify blocked loops with clearer unblock guidance | [Open Studio issues](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fstudio) |
| P0 | `area/workflow` | Harden default parameters and node ordering in official workflows | [Open Workflow issues](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fworkflow) |
| P1 | `area/neurokg` | Clean noisy edges/definitions and improve multihop quality | [Open NeuroKG issues](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fneurokg) |
| P1 | `area/hypothesis` | Improve novelty/factual quality and reduce predictive-model bias | [Open Hypothesis issues](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fhypothesis) |
| P1 | `area/datasets` | Increase dataset coverage and metadata completeness | [Open Dataset issues](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fdatasets) |
| P2 | `area/docs` | Improve docs/demo reproducibility and first-run onboarding | [Open Docs issues](https://github.com/zjc062/brain-researcher-public/issues?q=is%3Aissue+is%3Aopen+label%3Aarea%2Fdocs) |

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

## Label System

- `area/*`: where the issue belongs.
- `type/*`: bug, feature-request, scientific-review, discussion.
- `status/*`: maintainer lifecycle labels.

## Important Reviewer Rules

1. Use read-only review behavior unless explicitly asked to edit.
2. Do not click `Save governance` in Benchmark unless you are authorized.
3. Do not include PHI, secrets, or private credentials.
4. Include exact IDs wherever possible.

## Contributing and Governance

- Full contributor playbook: [CONTRIBUTING.md](CONTRIBUTING.md)
- Reviewer onboarding: [REVIEW_PLAYBOOK.md](REVIEW_PLAYBOOK.md)
- Benchmark task authoring: [benchmark/CONTRIBUTING_TASKS.md](benchmark/CONTRIBUTING_TASKS.md)
- Code of Conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- License: [LICENSE](LICENSE)
