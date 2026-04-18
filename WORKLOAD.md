# Workload — On-Call First-Responder Agent

The agent task for this lab. Deliberately narrow. The agent is the demo; the infrastructure around it is the point.

## What the agent does

Given a Prometheus alert payload, the agent produces a structured triage report and writes it to a ticket. Nothing more.

**Input:** Alertmanager webhook payload (alert name, labels, annotations, `startsAt`, related runbook URL if present).

**Output:** A triage record with fixed fields:
- Alert summary (one line, human-readable)
- Recent metric trend (last 30m, pulled live)
- Relevant log excerpts (last 10m from the offending service, by label match)
- Runbook reference (retrieved, not generated)
- Probable cause hypothesis (the one place the model gets to be creative)
- Suggested next step (from runbook if available, otherwise marked as inference)
- Confidence tier: `high` / `medium` / `low` / `insufficient-data`
- Tool-call ledger (every call, every response, every timing)

The last field is the point. The entire run is reconstructible from the record alone.

## Why this workload

- **Audit trail is load-bearing.** When the agent misreads an incident — and it will — the post-mortem needs a full replay. That's the whole pitch of the lab, demonstrated by the workload.
- **Tools are narrow and security-relevant.** Four tools (metric query, log fetch, runbook retrieve, ticket create). Each one is easy to scope, sandbox, and audit. No "give the agent a shell" nonsense.
- **Telemetry comes from the existing labs.** `sre-observability-lab` supplies the Prometheus + Loki substrate. `container-hardening-lab` patterns apply to the tool containers. The portfolio stops being siblings and becomes a stack.
- **Failure modes are narratable.** Hallucinated probable cause + confident tone is the classic agent failure. The audit trail + confidence tier + read-only tool scoping is how you survive it. Good blog material.
- **Boring in the correct way.** Not a "ChatGPT wrote my runbook" demo. The interesting content is the scaffolding.

## Tool surface

| Tool | Access | Sandboxing |
|---|---|---|
| `query_prometheus` | Read-only PromQL against a scoped Prometheus | Query allowlist by metric name prefix |
| `fetch_logs` | Read-only LogQL against Loki, time-bounded | Label selector required; rejects unbounded queries |
| `get_runbook` | Read-only retrieval from runbook store (S3 or Git) | Path prefix allowlist |
| `create_ticket` | Write to ticket backend (Jira-compatible API or local mock) | One ticket per run, rate-limited, labeled `agent-originated` |

No shell access. No code execution. No arbitrary HTTP. If the agent needs something outside this surface, the right answer is "expand the surface deliberately," not "give it curl."

## Non-goals

- No ticket triage quality benchmark. The agent can be wrong — the point is that wrong is safe.
- No training / fine-tuning loop. Base model + prompt + tools.
- No multi-agent orchestration. One agent, one run, one report.
- No real-time streaming into dashboards. Async is fine.

## What good looks like

- An alert hits the webhook → a triage record appears in the ticket system within 90 seconds
- Every step of the agent's reasoning is reconstructible from the audit log
- Killing the agent mid-run leaves no half-written state and no orphaned tool invocations
- Rerunning the same alert produces a similar (not identical) record — model nondeterminism is acknowledged, not papered over
- Revoking the agent's identity stops all four tools immediately — verifiable in the audit log of the tool side

## Dependencies on the runtime / framework eval

The workload shapes the runtime requirements:

- **Context length:** Modest. Alert + metric snapshot + logs + runbook fits in ~8k tokens for most cases; cap at 32k.
- **Tool calling:** Must be structured and typed. Free-form JSON is a footgun here.
- **Latency:** Target 90s end-to-end for the full loop. Streaming not required.
- **Concurrency:** 1–5 simultaneous runs is sufficient for the demo. Not a scaling story.

These feed into the runtime scorecard as pass/fail floors, not as comparative axes.
