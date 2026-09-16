# LocalAI v4.9.0 — Runtime Scorecard

**Environment:** Kubuntu (native Linux) · Docker 29.1.3 · i7-12700 · 31 GB RAM · CPU-only (Phase 1)
**Model under test:** `qwen2.5-3b-instruct-q4_k_m.gguf` (Q4_K_M, 1.9 GB, bartowski build from HuggingFace — same file used for Ollama and llama.cpp)
**Image:** `localai/localai:v4.9.0` — digest `sha256:d78cd113b2bc5892d7533c1356e9c9725bb90e86a075356a63730f3d681ce4d7`
**Eval date:** 2026-09-16

> Run on a different physical host than the Ollama/llama.cpp entries (native Kubuntu, not WSL2). Pre-filter gates and qualitative findings compare directly; absolute latency numbers do not.

## One-line verdict

**"An aggregator with real observability wins and the single scariest default of the three: an unauthenticated 39-tool admin agent, enabled out of the box."**

## Pre-filter — workload gates

| Gate | Requirement | Result |
|---|---|---|
| Context length | ≥ 32k supported | **PASS** — configured `context_size: 32768` in the model YAML, served without error |
| Tool calling | Typed / structured | **PASS** — 5/5 via OpenAI-compat `/v1/chat/completions` with `tools` |
| Latency p95 first-token | < 5s (3B CPU) | **PASS** — observed 0.06s |
| Latency p95 full | < 30s (3B CPU) | **PASS** — observed 3.25s |
| Concurrency | 5 simultaneous, no crash | **PASS** — 0 errors, 3.07x speedup |
| Container image | Official, versioned, pinnable | PASS (Docker Hub, digest-pinnable, self-identifying OCI labels) — but documented quickstart uses `:latest` |
| Maintainership | Commits in 90d, triaged issues | PASS — v4.9.0 shipped 2026-08-20, releases roughly every 1-2 weeks |
| CLI / headless | No desktop required | PASS |

**Pre-filter result: PASS.** Proceeding to scorecard.

## Scorecard

### Security / isolation

| Axis | Grade | Notes |
|---|---|---|
| Auth posture (default) | **F** | Zero API keys configured by default. Boot log literally says `no-auth single-user mode`. `--api-keys` / multi-user OIDC exist but are opt-in. |
| Model management auth | **F** | `POST /models/apply` (fetch + install from a URL) and `POST /models/delete/{name}` both return 200 with no credentials — the same class of issue as Ollama's disclosed GHSA-f6mr-38g8-39rg, not fixed here, just not (yet) written up as a CVE against this project. |
| Admin agent surface | **F** | In-process "LocalAI Assistant" MCP server: 39 tools, `read_only=false`, on by default (`--disable-local-ai-assistant` to turn off). Separate Agent Pool subsystem also on by default with its own reachable `/api/agent/*` endpoints. No other Phase 1 candidate ships an admin agent at all. |
| Bind address (host) | **C** | Documented `docker run` uses `-p 8080:8080` → publishes on 0.0.0.0. Same documentation-level footgun as the other two. |
| Bind address (container) | **F** | `--address=":8080"` default is all-interfaces. |
| Container user | **F** | Runs as `uid=0` (root). No `USER` directive. Third for three. |
| Backend supply chain | **F** | Installing the llama-cpp backend pulls a second OCI image from `quay.io` on a floating `:latest-cpu-llama-cpp` tag, and the CLI prints `installing OCI backend without signature verification` — cosign signing exists upstream but isn't verified by default (`--require-backend-integrity` is opt-in). |
| Secret handling | **B** | No runtime secret-management surface observed beyond API keys/auth config, which is itself opt-in. |
| Attack surface | **B** | 2 published GHSA advisories against `mudler/LocalAI`, both XSS, both LOW/MODERATE, both fixed in versions well below v4.9.0 (≤2.20.1, <2.22.0). Nothing outstanding. |
| DNS rebinding defense | **F** | No Origin-header check — same gap as llama.cpp. `curl -H 'Origin: evil.com'` returns 200. |
| Host header validation | **C** | Not separately verified beyond the Origin check above; treated as unproven rather than assumed safe. |
| CSRF middleware | **A** | On by default (`--disable-csrf` to turn off) — the only one of the three runtimes with this out of the box. |
| TLS | **C** | No TLS by default. Cleartext HTTP. Same as the other two. |
| Supply chain (main image) | **B** | Official Docker Hub image, self-identifying OCI version/revision labels. Did not verify Cosign signature on the main `localai/localai` image itself (separate from the backend-image finding above). |

### Resource governance

| Axis | Grade | Notes |
|---|---|---|
| Per-request token cap | **C** | `max_tokens` honored per request; no observed server-side hard cap. |
| Request timeout | **C** | No server-side request timeout enforcement observed. |
| Concurrent request limit | **B** | 5 concurrent requests ran clean; default thread pool sized to `threads=10` on this 20-core box, not separately tuned. |
| Backpressure | **B** | 0 errors, 3.07x speedup under 5x load, no OOM. |
| Context length default | **B** | Only tested with an explicit `context_size: 32768` in the model YAML — LocalAI does not auto-detect from GGUF metadata the way llama.cpp does; omitting the field is unverified here rather than assumed safe. |

### Observability

| Axis | Grade | Notes |
|---|---|---|
| Prometheus metrics endpoint | **A** | `/metrics` returns real Prometheus histograms, OTel-scoped, no flag required. Best of the three Phase 1 candidates on this axis. |
| Per-request token counts | **C** | `usage.completion_tokens` populated in streaming responses; `usage.prompt_tokens` consistently returned 0 across all 10 latency-probe runs. |
| Latency breakdown | Not observed | Did not find a per-request prefill/decode breakdown equivalent to Ollama's `eval_duration` or llama.cpp's `timings` object. |
| Structured logs | **C** | Colorized human-readable stdout logs, same as the other two. No JSON mode exercised. |
| OTel traces | Not tested | Metrics are OTel-scoped; did not verify a full trace export path. |
| Health endpoint | **A** | `/readyz` and `/healthz` both return 200; used directly by the image's own Docker `HEALTHCHECK`. |

### Operational

| Axis | Grade | Notes |
|---|---|---|
| Supported model formats | **A** | GGUF confirmed; README also claims safetensors, AWQ, GPTQ, MLX, and non-text modalities via other backends — not exercised here. |
| Model registration | **C** | A raw GGUF file dropped into the models directory is **not** auto-served — requires a hand-written YAML (`name`, `backend`, `parameters.model`). Rougher first-run than Ollama (`pull` handles it) or llama.cpp (`-m` flag, no config file). |
| Hot model swap | Not tested | Did not exercise the model gallery's install/swap flow beyond the reachability check on `/models/apply`. |
| Graceful shutdown | Not tested | Same TODO as the other two entries. |
| Multi-model serving | Not tested | Architecture supports it (backends are per-model processes); not exercised with a second model. |
| Quantization options | **A** | Full GGUF quant spectrum available externally, same as llama.cpp. |

### Deployment fit

| Axis | Grade | Notes |
|---|---|---|
| Official container image | **A** | Docker Hub, versioned, digest-pinnable, self-identifying labels. Quickstart itself uses `:latest`, same caveat as the others. |
| Helm chart | Not checked | Out of scope for this pass. |
| Idle RAM | **B** | 3.26 GiB resident with the 3B Q4 model loaded — higher than llama.cpp's ~2 GB for the same weights, attributable to the core API process plus a separate gRPC-connected backend process plus the always-on agent pool / assistant subsystem. |
| CPU-only viability | **A** | Ran cleanly on CPU; all pre-filter latency gates passed with room to spare. |
| K8s GPU integration | Not tested | GPU image variants exist (`-gpu-nvidia-cuda-13`, `-gpu-hipblas`, `-gpu-intel`, `-gpu-vulkan`); Phase 1 is CPU-only by design. |

### Adoption signal

| Axis | Grade | Notes |
|---|---|---|
| License | **A** | MIT. |
| Commit / release cadence | **A** | v4.9.0 shipped 2026-08-20; releases roughly every 1-2 weeks through 2026. Very active. |
| Maintainership | **A** | Core maintainer (mudler) plus a named team; large backend ecosystem (60+ backends) under active development. |
| Breaking-change frequency | **B** | Backend-split architecture (since v3.2.0) means the API surface has been broadly stable, but the per-backend OCI pull model is itself a relatively recent architectural shift worth watching on upgrade. |

---

## Tool-calling probe results (5/5)

All five cases passed via OpenAI-compat `/v1/chat/completions` with structured `tool_calls`:

- PASS: `query_prometheus` for metric trend
- PASS: `fetch_logs` for error investigation
- PASS: `get_runbook` by alert name
- PASS: `create_ticket` (same case Ollama failed on, same model, same quant — passes here, matching llama.cpp)
- PASS: `fetch_logs` with required `label_selector` arg

Same result shape as llama.cpp: the backend is llama.cpp under the hood, and LocalAI's chat templating handled tool-call rendering correctly out of the box, same as llama.cpp's `--jinja` default.

## Raw latency numbers

```
Endpoint: http://localhost:8080  Model: qwen2.5-3b-instruct-q4_k_m  Runs: 10 (+ 1 warmup)
Time to first token:  p50=0.05s  p95=0.06s  min=0.05s  max=0.07s
Total response time:  p50=2.86s  p95=3.25s  min=2.26s  max=3.34s
Output tokens:        p50=72     p95=82     mean=71
```

`usage.prompt_tokens` reported 0 on every run — an observability gap in the streaming response, not a functional failure (see raw notes).

Not directly comparable to the Ollama/llama.cpp numbers — different physical host (native Kubuntu i7-12700 here vs. WSL2 i9-12900H there). All three cleared their pre-filter gates by a wide margin; the interesting comparison is qualitative (see below), not the millisecond race.

## Narrative

LocalAI is what you'd expect from "aggregator wrapping best-in-class backends": it delegates the actual inference to llama.cpp (or vLLM, or whisper.cpp, or a dozen others) and spends its own effort on the platform layer around that — auth scaffolding, multi-user quotas, a model gallery, Prometheus metrics that actually work out of the box, an OpenAI-*and*-Anthropic-*and*-ElevenLabs-compatible API surface. On the axes that measure "does this feel like real infrastructure," it's the strongest of the three Phase 1 candidates: better metrics than either competitor, an image that tells you its own version, and a CSRF layer nobody asked for but which is there anyway.

Then you read the boot log. `no-auth single-user mode` is printed, not buried. `/models/apply` and `/models/delete/{name}` both take unauthenticated requests and queue real jobs — the same failure class as Ollama's disclosed CVE, just not (yet) the subject of one here. And then there's the part that doesn't have an analog in either other runtime: LocalAI boots an in-process admin agent with 39 tools and `read_only=false`, on by default, plus a whole separate Agent Pool subsystem with its own API, also on by default. This is a runtime built by a team that clearly understands agentic risk well enough to build quotas, RBAC, and per-user auth as real features — and ships all of it turned off, with an admin-capable agent turned *on*, as the default a busy engineer gets by running the documented command.

## Would I run this in a customer tenant?

**No, not as shipped, and not with the same confidence as the "yes, with caveats" verdicts for Ollama and llama.cpp.** The hardening path exists and looks more mature than either competitor's — real API-key and OIDC support, per-user quotas, RBAC — which argues this could become the best of the three once configured. But the gap between default and hardened is the widest of the three specifically because of the admin agent and the agent-pool subsystem: `--disable-local-ai-assistant`, `--disable-agents`, `--api-keys`, `--require-backend-integrity`, non-root custom image, localhost-only bind or a fronting proxy, and Kyverno admission checks refusing any pod that doesn't set all of the above. That's a longer flag list than either Ollama's or llama.cpp's hardening recipe, and unlike the other two, getting even one of those flags wrong here means an unauthenticated agent with 39 tools is reachable, not just an unauthenticated chat completion.

## Would this replace Ollama or llama.cpp for the lab's Phase 3 platform?

Not on its own. The agent-pool and assistant subsystems are exactly the kind of surface the lab's platform layer (Kyverno, the tool proxy, identity-scoped access) exists to constrain from the outside — running LocalAI's *own* built-in agent instead of building the lab's tool proxy would defeat the point of the lab. If LocalAI is used at all in Phase 3, it would be specifically for its inference serving (llama.cpp backend, same as evaluating llama.cpp directly) with `--disable-local-ai-assistant --disable-agents` baked into the image, not for its agent features.

## TODOs (not blocking)

- Graceful shutdown test (`SIGTERM` mid-inference)
- Verify `--api-keys` actually enforces 401 on missing/bad key
- Verify `--disable-local-ai-assistant` and `--disable-agents` actually close the surfaces described above (expect 404/disabled)
- Find and probe the actual WebUI-side chat endpoint the 39-tool Assistant answers on (not obviously `/v1/mcp/chat/completions`)
- Cosign signature verification on the main `localai/localai` image (separate from the backend-image finding already made)
- Re-run head-to-head on the same physical host as the Ollama/llama.cpp entries for a real latency comparison
- Phase 2 GPU rerun with a 7B model
