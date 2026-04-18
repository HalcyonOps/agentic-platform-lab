# Agentic Platform Lab — Charter

Status: **sketch.** Nothing built. Evaluation phase ongoing (see `EVAL_RUBRIC.md`).

## What this is

A lab that runs an agent workload on tenant-controlled, security-hardened infrastructure, end to end. The point is not the agent. The point is the infrastructure around the agent.

## Why it exists

Every enterprise wants to run agents. Almost none want to run them against a public API with their customer data as the context window. The actual operational question — *how do you host, scope, observe, and audit an agent you don't fully trust, running against data you do fully own* — is mostly unanswered in public examples.

Agent demos ignore infrastructure. Infrastructure demos ignore agents. This sits in the gap.

## What it demonstrates

- Tenant-hosted LLM runtime (no third-party API on the hot path)
- Agent framework on hardened Kubernetes, observable end to end
- Network isolation for tool execution (the agent can call things — not everything)
- Identity-scoped tool use (SPIFFE/SPIRE or equivalent — tools know which agent run they're serving)
- Resource limits, timeouts, kill switches
- Full audit trail: every prompt, every tool call, every response, reconstructible from telemetry alone
- Policy enforcement (Kyverno) on anything deployed into the agent's blast radius

The workload itself is deliberately boring. An agent processes a work item, calls two tools, writes a report. The boringness is the point — the interest is the scaffolding.

## Hard constraints

1. **Tenant-controlled.** Inference runtime lives inside the same trust boundary as the data. No third-party API dependency for the main loop.
2. **Laptop-first, cloud-second.** Must run on Kind on a reasonable laptop. Cloud is an extension, not a precondition.
3. **No hand-waved security story.** If the README says "identity-scoped tool calls," the reader can point at the file that enforces it.
4. **Boring workload.** The scaffolding is the content. Don't get clever with the agent task.
5. **Observability is not optional.** Every agent run must be reconstructible from telemetry alone — no log-diving heroics required.

## Non-goals

- Not a new agent framework
- Not a new LLM runtime
- Not a benchmark
- Not a production-ready platform — it's a lab, with the honesty that implies

## Relationship to existing labs

Upstream dependencies, not siblings. If this lab works, the others become its receipts.

| Lab | Role here |
|---|---|
| `container-hardening-lab` | Agent runtime + tool containers use the hardened base patterns |
| `k8s-bootstrap-lab` | The platform this runs on |
| `mlops-pipeline-lab` | Model serving patterns extend here |
| `sre-observability-lab` | SLO and alert patterns apply to agent runs |
| `iac-security-lab` | Any cloud-side extension uses these policies |

## Success criteria

- A reader with no ML background can follow the infrastructure story
- A reader with no infra background can see why the ML-side choices matter
- A hiring manager can point at this and say "yes, this person understands both halves"
- `make up` just works on a reasonable laptop
- Any agent run's audit trail can be produced as a single artifact

## Open decisions

- Runtime: pending evaluation (see `EVAL_RUBRIC.md`)
- Agent framework: pending evaluation
- Workload domain: **decided — on-call first-responder agent.** See `WORKLOAD.md`. Consumes telemetry from `sre-observability-lab`, narrow four-tool surface, audit trail is load-bearing. Chosen over compliance triage because it makes the existing portfolio interlock instead of sitting adjacent.
- Identity layer: **decided — K8s ServiceAccounts + OPA at the tool proxy.** SPIFFE/SPIRE deferred, not rejected. See `decisions/0001-agent-identity-and-tool-authz.md`.
- Public vs. private during build: start private, move to public once the first end-to-end loop works and the story is defensible
