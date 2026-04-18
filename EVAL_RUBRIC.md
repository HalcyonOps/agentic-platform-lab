# Evaluation Rubric — Local LLM Runtimes & Agent Frameworks

The axes below are weighted for **DevSecOps fit**, not raw throughput. A runtime that serves 3x tokens/sec but binds 0.0.0.0 with no auth out of the box scores worse here than a slower one that ships with sane defaults.

### Editorial stance: hardened-by-default > hardenable

Score the defaults, not the ceiling. "Can be configured securely" is not the same as "safe to install." Everyone knows nobody is going to read config as carefully as they should — so a tool that requires substantial hardening out of the box is shipping an attack surface, regardless of how well-documented the hardening path is. That is the lesson of the Trivy incident and it is the frame here. A high ceiling does not redeem a low floor.

When scoring, ask: *if a competent-but-busy engineer pulls this container and runs it with the official Helm chart, are they safe?* If no, that is the grade — not what they could achieve after a weekend of config hardening.

Scoring: `A` (strong / default-safe), `B` (workable / documented), `C` (footgun / requires deliberate hardening), `F` (disqualifying).

### Pre-filter — workload-driven pass/fail gates

Run these before the full scorecard. A runtime that fails any of them is out, no matter how it scores on the axes below. Scoped to the workload in `WORKLOAD.md` (on-call first-responder agent).

| Gate | Requirement | Rationale |
|---|---|---|
| Context length | ≥ 32k tokens | Alert + metric snapshot + logs + runbook fits in ~8k typical, 32k ceiling for edge cases |
| Tool calling | Typed / structured (JSON schema or equivalent) enforced by the runtime | Free-form tool output is a footgun for the audit trail and for policy enforcement |
| Inference latency | p95 first-token < 5s, p95 full response < 30s on a single request at target model size | 90s end-to-end budget for the full loop; inference cannot dominate |
| Concurrency | 5+ simultaneous requests without crash or OOM at target model size | Five is the upper bound for the lab; no crash behavior under that is disqualifying |
| Container image | Officially maintained, versioned, pinnable | A project that expects you to build from source is not lab-ready |
| Maintainership | Commits in the last 90 days, issues triaged | Abandoned or stale projects are disqualified regardless of quality |
| CLI / headless | Fully operable with no desktop session, no GUI dependency | Tenant-hosted inference must be scriptable end-to-end; anything requiring a desktop is disqualified |

Pre-filter results should be captured per-runtime as `PASS` / `FAIL (gate: reason)`. A `FAIL` means the runtime is eliminated — do not spend further effort on the scorecard.

---

## Part 1 — Local LLM Runtime

### Candidates

- Ollama
- vLLM
- HuggingFace TGI (Text Generation Inference)
- llama.cpp server (`llama-server`)
- LocalAI

LM Studio was considered and **dropped**: it's GUI-primary. Tenant-hosted inference must be fully headless and scriptable — anything that expects a desktop session is disqualified before the scorecard.

### Axes

#### Security / isolation
- **Auth posture out of the box.** None / API key / mTLS / pluggable?
- **Bind address default.** `127.0.0.1` or `0.0.0.0`?
- **Container user.** Runs as root or non-root by default?
- **Secret handling.** How do model weights, config, and downstream API keys get in — env, file, mounted secret?
- **Attack surface.** File upload endpoints, Jinja/template execution, known CVEs in the last 12 months, how quickly patched.
- **Supply chain.** Official image signed? SBOM available? Build provenance?

#### Resource governance
- Per-request token cap (input + output)
- Per-request wall-clock timeout
- Max concurrent requests / queue depth
- GPU memory cap enforcement
- Backpressure behavior under overload (drop / queue / OOM)

#### Observability
- Prometheus metrics endpoint
- Per-request token counts exposed in metrics
- Latency breakdown (queue / prefill / decode) visible
- Structured logs (JSON, correlation IDs)
- OpenTelemetry trace export

#### Operational
- Supported model formats (GGUF, safetensors, AWQ, GPTQ)
- Model swap: hot-reload or restart?
- Graceful shutdown — drains in-flight requests?
- Multi-model serving in one process
- Quantization options and quality impact documented

#### Deployment fit
- Official container image — maintained, versioned, pinnable
- Helm chart quality (official or community-of-one?)
- Idle footprint (RAM, VRAM)
- CPU-only viability for dev workflow
- Kubernetes Device Plugin / GPU operator compatibility

#### Adoption signal
- License (Apache / MIT / source-available / custom)
- Commit cadence and release cadence (last 90 days)
- Maintainer count and responsiveness to issues
- Breaking-change frequency in the last 12 months

### Output format

For each runtime:

1. One-line verdict (the kind that reads well as a blog headline)
2. Scorecard table across the axes above
3. Short narrative — two paragraphs, opinionated, voice-on. Lead with the most interesting footgun or win. This is the part that makes it a teardown, not a spec sheet.
4. "Would I run this in a customer tenant?" — yes / yes-with-caveats / no — and the one-line reason.

---

## Part 2 — Agent Framework (lighter, separate pass)

### Candidates

- LangGraph
- CrewAI
- OpenAI Agents SDK
- Claude Agent SDK
- Plain function-calling loop (baseline to measure the others against)

### Axes

- **Tool-calling model.** Typed schemas? Free-form? Parallel calls?
- **State model.** Stateless, checkpointed, resumable after crash?
- **Human-in-the-loop.** First-class or bolted on?
- **Observability hooks.** Where do you inject tracing / logging / audit?
- **Model coupling.** Model-agnostic or tied to one provider?
- **Tool sandboxing.** What does the framework assume about tool trust?
- **Production signal.** Anyone running it at scale? Known failure modes?

### Output format

Same shape as runtime evaluation but abbreviated — the interesting question is fit for this lab, not a comprehensive market review.

---

## How to run this

1. Spin each runtime on Kind (or bare Docker) with default settings. Don't harden anything yet — scoring the defaults is the point.
2. Fire 10 requests through a consistent test harness. Capture metrics, logs, traces as emitted.
3. Fill in the scorecard against the axes above.
4. Write the narrative last, from notes taken during the run. Do not sanitize — if it pissed you off, that goes in.
5. Runtime pick = whichever wins on security/observability axes *and* clears the operational floor. Throughput is a tiebreaker, not a driver.

## Rules for this eval

- Defaults matter. If a runtime needs 40 lines of config to be safe, that is the story.
- Test the boring paths. Graceful shutdown, OOM recovery, model swap under load.
- Document what you *didn't* test — unknowns are part of the scorecard.
- Keep raw notes. They become the blog post later; post-hoc reconstruction loses the real reactions.
