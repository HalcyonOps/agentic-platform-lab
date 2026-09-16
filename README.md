# agentic-platform-lab

> An agent workload running on tenant-controlled, security-hardened Kubernetes infrastructure. Sketch phase — charter, workload, and runtime evaluation are in; the platform build is next.

## What this lab is for

Most "agentic AI" demos today ship with an API key, a vendor SDK, and a handwave where the security posture should be. This lab takes the opposite position: build the smallest honest agent workload I can defend, run it on infrastructure the tenant (not a vendor) controls, and force every piece of it to justify its existence against a real threat model.

The thesis is that the interesting DevSecOps+AI work is not "prompt engineering" and not "ML in a Jupyter notebook" — it's the admission policies, identity model, network segmentation, observability, and supply-chain discipline that an agent workload needs to run somewhere that isn't someone else's laptop. That story doesn't get told much. This lab is my attempt to tell it.

## Status

**Phase 1 — runtime evaluation (done).** CPU-only, 3B Q4 models. Charter and rubric closed; all three CPU candidates evaluated.

| Runtime | Status | One-line verdict |
|---|---|---|
| [Ollama 0.21.0](eval/results/ollama.md) | Done | Fast, friendly, zero auth, silently clamps 32k context to 2k by default. |
| [llama.cpp b8833](eval/results/llama-cpp.md) | Done | Faster engine, more hardening levers, `/slots` endpoint leaks live prompts by default. |
| [LocalAI v4.9.0](eval/results/localai.md) | Done | Best metrics of the three, and the only one that ships an unauthenticated 39-tool admin agent by default. |
| vLLM | Phase 2 (GPU-required) | — |
| TGI | Phase 2 (GPU-required) | — |

**Phase 2 — GPU runtime evaluation.** Blocked on WSL2 GPU passthrough setup. Reruns Phase 1 candidates with a 7B Q4 model and adds vLLM + TGI.

**Phase 3 — the platform itself.** Kyverno admission policies, hardened container image for the chosen runtime, authenticated tool proxy, agent workload wired against the four tools defined in [`TOOLS.md`](TOOLS.md), running end-to-end inside Kind or EKS. Not started.

## Editorial stance

The rubric in [`EVAL_RUBRIC.md`](EVAL_RUBRIC.md) weights **safe-by-default** above **hardenable.** A tool that can be locked down with enough configuration is not the same as a tool that ships locked down, because nobody reads config as carefully as they should. Every runtime evaluation in this lab answers the question: *if a competent-but-busy engineer runs the documented default install, are they safe?*

All three Phase 1 candidates fail that question. They fail differently, which is the interesting part — and the failure modes are what the platform layer exists to compensate for.

## Repository layout

```
CHARTER.md            Purpose, constraints, what's in and out of scope
WORKLOAD.md           The agent task spec — on-call first-responder
TOOLS.md              Four-tool surface: query_prometheus, fetch_logs,
                      get_runbook, create_ticket
EVAL_RUBRIC.md        How runtimes are graded (safe-by-default weighted)
decisions/            Architectural decision records
  0001-agent-identity-and-tool-authz.md
eval/
  EVAL_PLAN.md        Two-phase (CPU then GPU) evaluation plan
  harness/            Reusable probes for any OpenAI-compatible runtime
    latency_probe.py       p50/p95 TTFT + total, streaming
    tool_calling_probe.py  Typed tool-call reliability
    concurrency_probe.py   5-way simultaneous request behavior
  raw-notes/          Reaction-as-it-happens notes per runtime
  results/            Scorecards per runtime
  models/             GGUF files, gitignored
```

## Agent workload in one paragraph

An on-call first-responder agent that receives a structured Prometheus alert and produces a triage report within a 90-second budget. It can call four read-mostly tools through a policy-enforced proxy: query Prometheus, fetch Loki logs, retrieve a runbook, and file one ticket. No shell access, no arbitrary HTTP, no Kubernetes API. The workload is deliberately boring — it exists to produce legible failure modes for the platform to catch, not to impress anyone with agent capability.

## Companion repos

This lab reads against others in the same portfolio:

- **[sre-observability-lab](https://github.com/R055LE/sre-observability-lab)** — upstream data source. The alert payloads the agent processes are shaped by the SLO/burn-rate work there.
- **[k8s-bootstrap-lab](https://github.com/R055LE/k8s-bootstrap-lab)** — the platform layer the agent workload will land on.
- **[container-hardening-lab](https://github.com/R055LE/container-hardening-lab)** — where the runtime image gets its hardening (non-root, distroless where possible, Cosign, SBOM).
- **[mlops-pipeline-lab](https://github.com/R055LE/mlops-pipeline-lab)** — same deployment discipline applied to a classic ML model; this lab is the agentic counterpart.

## Running the harness

```bash
# Example: point any OpenAI-compatible runtime at the probes
python3 eval/harness/latency_probe.py \
  --endpoint http://localhost:8081 \
  --model qwen2.5-3b-instruct-q4_k_m.gguf \
  --api openai

python3 eval/harness/tool_calling_probe.py \
  --endpoint http://localhost:8081 \
  --model qwen2.5-3b-instruct-q4_k_m.gguf

python3 eval/harness/concurrency_probe.py \
  --endpoint http://localhost:8081 \
  --model qwen2.5-3b-instruct-q4_k_m.gguf \
  --api openai --concurrent 5
```

The probes speak both Ollama-native (`--api ollama`) and OpenAI-compatible (`--api openai`) endpoints. `tool_calling_probe.py` is OpenAI-compat only — it's specifically testing structured `tool_calls` output.

## Not in scope

- Training, fine-tuning, or quantizing models. This is a deployment/ops lab.
- Latency-critical inference. 90-second budget assumes an on-call triage workflow, not a user-facing chat path.
- Multi-agent orchestration. One agent, four tools, one output.
- Vendor-hosted agent frameworks. "Tenant-controlled" is the whole point.
