# Ollama v0.21.0 — Runtime Scorecard

**Environment:** WSL2 Ubuntu on Windows · Docker 29.1.3 · i9-12900H · 31 GB RAM · CPU-only (Phase 1)
**Model under test:** `qwen2.5:3b` (Q4_K_M, 1.9 GB)
**Image:** `ollama/ollama:0.21.0` — digest `sha256:d3d553bdfbcc7f55dd5ddf42c4cbe3a927aa9bb1802710d35e94656ca5aea02b`
**Eval date:** 2026-04-17

## One-line verdict

**"Fast to start, fast to serve, and fast to hand an attacker the keys — Ollama's defaults are a security appliance aimed at your foot."**

## Pre-filter — workload gates

| Gate | Requirement | Result |
|---|---|---|
| Context length | ≥ 32k supported | **PASS** (native 32k) — but see defaults footgun below |
| Tool calling | Typed / structured | PASS (OpenAI-compatible `/v1/chat/completions` with `tools`) |
| Latency p95 first-token | < 5s (3B CPU) | **PASS** — observed 0.28s |
| Latency p95 full | < 30s (3B CPU) | **PASS** — observed 9.77s |
| Concurrency | 5 simultaneous, no crash | **PASS** — 0 errors, 3.77x speedup |
| Container image | Official, versioned, pinnable | PASS (Docker Hub, SHA256 digest available, tag `0.21.0`) |
| Maintainership | Commits in 90d, triaged issues | PASS (v0.21.0 shipped 2026-04-16, day before eval) |
| CLI / headless | No desktop required | PASS |

**Pre-filter result: PASS.** Proceeding to scorecard.

## Scorecard

### Security / isolation

| Axis | Grade | Notes |
|---|---|---|
| Auth posture (default) | **F** | No authentication on any endpoint. All of `/api/tags`, `/api/ps`, `/api/version`, `POST /api/pull`, `DELETE /api/delete`, `POST /api/create` reachable unauthenticated. Critical advisory GHSA-f6mr-38g8-39rg describes exactly this posture. |
| Bind address (host) | **C** | Documented `docker run` uses `-p 11434:11434` → publishes on 0.0.0.0. Users must know to use `-p 127.0.0.1:11434:11434`. |
| Bind address (container) | **F** | `OLLAMA_HOST=0.0.0.0:11434` baked into image. Any co-tenant container on the same network reaches it regardless of host port binding. |
| Container user | **F** | Runs as `uid=0` (root). No `USER` directive in image. |
| Secret handling | **B** | Model weights verified by SHA256 on pull. No runtime secret-management surface — nothing to leak or mishandle. |
| Attack surface | **C** | 14 published GHSA advisories against the Go package. 1 critical, 8 high, 4 medium. Most are in older versions; current v0.21.0 is not directly listed, but the critical auth issue is by design rather than a patchable bug. |
| DNS rebinding defense | **A** | Origin-based rebinding check works correctly. Browser attack vector closed. |
| Host header validation | **C** | No Host header enforcement for non-browser clients. Defense-in-depth gap if an L7 proxy is misconfigured. |
| TLS | **C** | No TLS by default. Cleartext HTTP on 11434. Expected to be terminated externally. |
| Supply chain | **C** | Official image. Did not observe Cosign signatures on Docker Hub. No SBOM referenced from image labels. |

### Resource governance

| Axis | Grade | Notes |
|---|---|---|
| Per-request token cap | **C** | `num_predict` honored per request but no server-side hard cap; a client can request arbitrary output length. |
| Request timeout | **C** | No server-side request timeout enforcement observed. Long-running requests run to completion. |
| Concurrent request limit | **B** | Defaults to 4 parallel slots (`OLLAMA_NUM_PARALLEL=4`), extras queue cleanly. Configurable. |
| Backpressure | **B** | Observed queueing, no errors, no OOM under 5x load. |
| Context length default | **F** | **`num_ctx=2048` default on a model with 32k native context.** Silent truncation unless caller knows to set it. Classic Ollama footgun. |

### Observability

| Axis | Grade | Notes |
|---|---|---|
| Prometheus metrics endpoint | **F** | `/metrics` returns 404. No Prometheus-format metrics. |
| Per-request token counts | **B** | Returned in API response (`eval_count`, `prompt_eval_count`) but not exported as metrics. Client-side aggregation only. |
| Latency breakdown | **B** | `total_duration`, `load_duration`, `prompt_eval_duration`, `eval_duration` returned per response. Useful for per-request analysis; no aggregation. |
| Structured logs | **C** | Logs to stdout in human-readable format. No JSON mode observed. |
| OTel traces | **F** | No trace export. |

### Operational

| Axis | Grade | Notes |
|---|---|---|
| Supported model formats | **A** | GGUF via `ollama pull`; bring-your-own via `Modelfile`. |
| Hot model swap | **A** | Different model on each request; Ollama manages memory residency automatically. |
| Graceful shutdown | Not tested | Did not interrupt mid-inference. TODO. |
| Multi-model serving | **A** | Multiple models loaded as needed, with LRU eviction. |
| Quantization options | **B** | Q4/Q5/Q8 variants available via tag, but only via model registry — no on-the-fly quantization. |

### Deployment fit

| Axis | Grade | Notes |
|---|---|---|
| Official container image | **A** | Maintained, versioned, pinnable by tag and digest. |
| Helm chart | N/A | No official chart. Community charts exist. |
| Idle RAM | **A** | ~35 MB resident when no model loaded. |
| CPU-only viability | **A** | Runs cleanly on CPU, including quantized models. 20-core i9 handles 3B at ~10 tok/s. |
| K8s GPU integration | **B** | Env vars for NVIDIA device plugin pre-set in image. Tested indirectly. |

### Adoption signal

| Axis | Grade | Notes |
|---|---|---|
| License | **A** | MIT. |
| Commit / release cadence | **A** | v0.21.0 shipped 2026-04-16. Active. |
| Maintainership | **A** | Core team + community. Issues triaged. |
| Breaking-change frequency | **B** | Minor versions occasionally shift API shape but documented. |

---

## Tool-calling probe results (4/5)

- PASS: `query_prometheus` for metric trend (though generated PromQL was garbage — `payments_p95_latency_us_over_time(range(-30m:now)` is invented syntax)
- PASS: `fetch_logs` for error investigation
- PASS: `get_runbook` by alert name
- **FAIL: `create_ticket`** — model returned the tool-call JSON in the `content` field as plain text, not as a `tool_calls` array. Runtime's structured parsing didn't catch it.
- PASS: `fetch_logs` with required `label_selector` arg

The failure is a 3B model reliability issue, not a runtime issue. The machinery works; the small model is the bottleneck. Takeaway: **production workload needs 7B+ class for reliable tool calling.** Which means GPU phase. Which means we have a Phase 2 marker already.

## Raw latency numbers

```
Endpoint: http://localhost:11434  Model: qwen2.5:3b  Runs: 10 (+ 1 warmup)
Time to first token:  p50=0.24s  p95=0.28s  min=0.19s  max=0.29s
Total response time:  p50=6.28s  p95=9.77s  min=4.89s  max=11.23s
Output tokens:        p50=82    p95=97     mean=82
```

Cold load: ~8.4s one-time. Steady-state is snappy.

## Narrative

Ollama is genuinely good software wrapped in defaults that would get you fired in a security review. The inference works, the API is clean, the model management is frictionless, and SHA256 digest verification on model pulls is the right default. The DNS rebinding fix is in place. The tool-calling API is standards-compliant. On a 20-core CPU it serves a 3B model fast enough that you can develop against it without hating your life.

And then there's everything else. The documented quickstart command exposes it on every host interface. The container runs as root. The server inside binds `0.0.0.0`, so even a corrected host port mapping doesn't isolate it. There is no authentication — not weak authentication, not optional authentication, just none. The metrics endpoint returns 404. Your 32k-context model silently becomes a 2k-context model unless you read enough of the API docs to know `num_ctx` isn't negotiable. If you asked a hiring manager to list the defaults they'd want from a production inference runtime, Ollama would fail on seven of ten answers — and the response from the project is "put a reverse proxy in front, you." Which, fine, but that's a security posture dressed up as a philosophy.

## Would I run this in a customer tenant?

**Yes, with caveats.** The caveats are load-bearing: build a custom image that drops to a non-root user, override `OLLAMA_HOST` to localhost-only inside the container, deploy behind an authenticated reverse proxy (the Lab's tool proxy can do double duty), expose a sidecar metrics exporter, enforce `num_ctx` at the client layer, and wrap the whole thing in Kyverno policies that refuse to admit pods not conforming to those choices.

At that point you've built a small hardening layer. The question is whether that layer is a liability or a feature for the lab. **Feature.** The Kyverno-enforces-the-hardening story is its own blog post, and it's exactly the DevSecOps-meets-AI narrative the portfolio wants to tell.

## TODOs (not blocking)

- Graceful shutdown test (`SIGTERM` mid-inference, observe draining behavior)
- Model swap under load
- Image provenance — Cosign signature and SBOM availability
- `OLLAMA_NUM_PARALLEL` / `OLLAMA_MAX_LOADED_MODELS` envelope testing under heavier concurrency
- Phase 2 GPU rerun with a 7B model
