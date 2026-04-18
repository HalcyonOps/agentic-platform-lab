# Tool Surface — On-Call First-Responder Agent

Four tools. Each one is scoped, audited, and called through a proxy — the agent never talks to Prometheus, Loki, the runbook store, or the ticket system directly. The proxy is where identity, policy, rate-limiting, and audit live.

## Shared contract

Every tool call, inbound and outbound, conforms to the following envelope. No exceptions.

### Request envelope (agent → proxy)

```json
{
  "run_id": "uuid — issued once per agent invocation",
  "tool": "query_prometheus | fetch_logs | get_runbook | create_ticket",
  "args": { ... tool-specific ... }
}
```

The `run_id` is not set by the agent — it is injected by the proxy from the verified SA token claims. If the agent tries to set it, the proxy rejects.

### Response envelope (proxy → agent)

```json
{
  "ok": true,
  "data": { ... tool-specific ... },
  "meta": {
    "tool": "query_prometheus",
    "latency_ms": 142,
    "truncated": false
  }
}
```

### Error envelope

```json
{
  "ok": false,
  "error": {
    "code": "policy_denied | rate_limited | upstream_error | invalid_args | timeout",
    "message": "human-readable",
    "retryable": false
  }
}
```

Errors are always the envelope, never raw upstream exceptions. Agents reason better against a fixed error vocabulary.

### Audit log (proxy → audit store, every call)

```json
{
  "run_id": "...",
  "tool": "...",
  "args_hash": "sha256 of args",
  "args": { ... },
  "response_hash": "sha256 of data",
  "response": { ... },
  "latency_ms": 142,
  "outcome": "ok | error:code",
  "timestamp": "RFC3339"
}
```

The audit log is the ground truth for any post-mortem. A run is the ordered set of its audit records plus the final triage report.

---

## `query_prometheus`

Read-only PromQL against a scoped Prometheus.

### Args

```json
{
  "query": "rate(http_requests_total[5m])",
  "range": {
    "start": "RFC3339 | 'now-30m'",
    "end": "RFC3339 | 'now'",
    "step": "duration, e.g. '30s'"
  }
}
```

`range` omitted = instant query.

### Constraints enforced by proxy

- Metric name in the query must start with an allowlisted prefix. Default allowlist: `http_`, `process_`, `container_`, `node_`, `up`, plus per-deployment extensions.
- Max range: 30 minutes.
- Max samples returned: 1,000. Truncation is indicated in `meta.truncated`.
- Upstream timeout: 10 seconds.
- No recording-rule creation, no alert creation, no admin endpoints — only `/api/v1/query` and `/api/v1/query_range`.

### Failure modes

- Query fails allowlist → `policy_denied`
- Query exceeds time budget → `timeout`
- Upstream Prometheus error → `upstream_error`

---

## `fetch_logs`

Read-only LogQL against Loki, time-bounded and label-scoped.

### Args

```json
{
  "label_selector": "{app=\"payments\", env=\"prod\"}",
  "filter": "optional LogQL filter expression",
  "start": "RFC3339 | 'now-10m'",
  "end": "RFC3339 | 'now'",
  "limit": 200
}
```

### Constraints enforced by proxy

- `label_selector` must include at least one of: `app`, `service`, `component`. Bare `{}` or overly broad selectors are rejected.
- Max range: 10 minutes.
- Max lines returned: 500. Hard cap overrides requested `limit`.
- Upstream timeout: 10 seconds.
- No write endpoints. No tail/stream — bounded fetches only.

### Failure modes

- Selector missing required labels → `invalid_args`
- Range exceeds cap → `invalid_args`
- Upstream Loki error → `upstream_error`

---

## `get_runbook`

Read-only retrieval from a runbook store (S3 prefix, Git repo, or local directory — backing is configurable).

### Args

```json
{
  "path": "runbooks/payments/high-latency.md"
}
```

Alternatively:

```json
{
  "alert_name": "PaymentsP95LatencyHigh"
}
```

The proxy resolves `alert_name` → `path` via a versioned mapping file. Agent never chooses paths outside the mapping.

### Constraints enforced by proxy

- `path` must begin with `runbooks/`.
- Max retrieval size: 64 KB per call.
- Unknown alert names return `not_found` via `upstream_error` — no fallback, no fuzzy match.
- Response includes source URI so the triage report can cite the runbook.

### Failure modes

- Path outside allowlist → `policy_denied`
- Alert name not in mapping → `upstream_error` (code: `not_found`)
- Retrieval exceeds size cap → `upstream_error` (code: `too_large`)

---

## `create_ticket`

Write-only to a specific project/queue in the ticket backend. The agent cannot read, edit, or delete tickets — the proxy does not expose those capabilities.

### Args

```json
{
  "title": "One-line summary",
  "body": "Markdown body — the full triage report",
  "labels": ["agent-originated", "oncall-triage", "..."],
  "priority": "low | normal"
}
```

### Constraints enforced by proxy

- `agent-originated` label is auto-applied by the proxy whether or not the agent includes it.
- `priority` is capped at `normal`. `high` / `critical` / `P0` / `P1` are rejected — an agent cannot escalate blast radius on its own.
- One ticket per `run_id`. A second `create_ticket` call in the same run returns `policy_denied`.
- Target project/queue is configured server-side, not agent-controlled.

### Failure modes

- Priority above cap → `policy_denied`
- Second ticket in a run → `policy_denied`
- Upstream ticket API error → `upstream_error`

---

## What is explicitly not a tool

These are the things people reflexively add and the lab deliberately excludes:

- **Shell / code execution.** No.
- **Arbitrary HTTP fetch.** No.
- **Kubernetes API access.** No — the agent does not diagnose cluster state directly; it reads metrics and logs.
- **Alert acknowledgement / silencing.** No. Mutating alert state belongs to humans.
- **Paging / escalation.** No. The ticket is the output; whatever routing exists downstream is a human concern.

If a future iteration of the workload needs any of these, the answer is "add it to this file with a threat model and policy," not "give the agent a more general tool."
