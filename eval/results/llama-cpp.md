# llama.cpp server b8833 — Runtime Scorecard

**Environment:** WSL2 Ubuntu on Windows · Docker 29.1.3 · i9-12900H · 31 GB RAM · CPU-only (Phase 1)
**Model under test:** `Qwen2.5-3B-Instruct-Q4_K_M.gguf` (1.9 GB, bartowski build from HuggingFace)
**Image:** `ghcr.io/ggml-org/llama.cpp:server` — digest `sha256:e25ab0c4bcbe82fc766f1683a9d889bd5a0a8c76130906cd9299a1f6d7dbbffc`
**Eval date:** 2026-04-17

## One-line verdict

**"Faster than Ollama, more honest about hardening levers, and shipping a live prompt-leak endpoint on by default — a serious engine wearing a cheap suit."**

## Pre-filter — workload gates

| Gate | Requirement | Result |
|---|---|---|
| Context length | ≥ 32k supported | **PASS** — native 32768, honored by default (no silent clamp) |
| Tool calling | Typed / structured | **PASS** — 5/5 via OpenAI-compat `/v1/chat/completions` with `tools`, `--jinja` on by default |
| Latency p95 first-token | < 5s (3B CPU) | **PASS** — observed 0.33s |
| Latency p95 full | < 30s (3B CPU) | **PASS** — observed 6.02s |
| Concurrency | 5 simultaneous, no crash | **PASS** — 0 errors, 4.25x speedup |
| Container image | Official, versioned, pinnable | PASS (GHCR, digest-pinnable) — but `:server` tag is floating, no version in image labels |
| Maintainership | Commits in 90d, triaged issues | PASS (5 builds on 2026-04-17 alone) |
| CLI / headless | No desktop required | PASS |

**Pre-filter result: PASS.** Proceeding to scorecard.

## Scorecard

### Security / isolation

| Axis | Grade | Notes |
|---|---|---|
| Auth posture (default) | **F** | No authentication on any endpoint. `/v1/models`, `/v1/chat/completions`, `/completion`, `/props`, `/slots` all reachable without credentials. |
| Auth posture (hardenable) | **B** | `--api-key` / `--api-key-file` are first-class server flags. Better hardening surface than Ollama, which has zero built-in auth. |
| Bind address (host) | **C** | Documented `docker run` uses `-p 8080:8080` → publishes on 0.0.0.0. Same documentation-level footgun as Ollama. |
| Bind address (container) | **F** | `LLAMA_ARG_HOST=0.0.0.0` baked into image. Any co-tenant container on the same network reaches it regardless of host-port binding. `--host /path/to/unix.sock` is available as a hardening option, but not default. |
| Container user | **F** | Runs as `uid=0` (root). No `USER` directive in image. Same as Ollama. |
| Slots data leak | **F** | **`/slots` endpoint enabled by default** and returns full slot state including other users' prompts and completions. Data-leakage vector in any shared-network deployment. `--no-slots` closes it. |
| Secret handling | **A** | No runtime secret-management surface. Model files bring-your-own, verified out-of-band (HuggingFace repo signatures / manual SHA256). |
| Attack surface | **B** | Zero published GHSA advisories against `ggerganov/llama.cpp` or `ggml-org/llama.cpp`. Interpret charitably (less deployed in sensitive contexts) or skeptically (less external scrutiny). |
| DNS rebinding defense | **F** | **No Origin-header check.** `curl -H 'Origin: http://evil.com'` returns 200. Browser cross-origin attacks are *not* blocked. Worse than Ollama's posture. |
| Host header validation | **C** | No Host-header enforcement. Defense-in-depth gap. Same as Ollama. |
| TLS | **C** | No TLS by default. Cleartext HTTP. Expected to be terminated externally. |
| Supply chain | **C** | Official GHCR image. `:server` tag floats — only digest pinning gives reproducibility. Image labels do not self-identify the llama.cpp version (only the Ubuntu base). No observed Cosign signature or SBOM. |

### Resource governance

| Axis | Grade | Notes |
|---|---|---|
| Per-request token cap | **C** | `max_tokens` / `n_predict` honored per request; no server-side hard cap. |
| Request timeout | **C** | No server-side request timeout enforcement observed. |
| Concurrent request limit | **B** | 4 parallel slots default. Configurable via `--parallel`. |
| Backpressure | **B** | 5 concurrent ran clean, 4.25x speedup, 0 errors. |
| Context length default | **A** | **32k honored automatically from GGUF metadata.** No silent clamp. Direct contrast with Ollama's 2048 default. |

### Observability

| Axis | Grade | Notes |
|---|---|---|
| Prometheus metrics endpoint | **C** | `/metrics` returns 501 by default. Flipping `--metrics` makes it Prometheus-compatible. Capability present, gated by flag. |
| Per-request token counts | **A** | Returned in OpenAI-compat `usage` block (`completion_tokens`, `prompt_tokens`). |
| Latency breakdown | **B** | `timings` object in response: prompt/predict durations. Per-request, no aggregation. |
| Structured logs | **C** | Logs to stdout in human-readable format. No JSON mode observed. |
| OTel traces | **F** | No trace export. |
| Health endpoint | **A** | `GET /health` returns `{"status":"ok"}`. K8s-probe-ready out of the box. |

### Operational

| Axis | Grade | Notes |
|---|---|---|
| Supported model formats | **A** | GGUF. Bring-your-own from HuggingFace or any artifact registry. |
| Hot model swap | **C** | Single-model server. Restart to change models. (Ollama's LRU multi-model story is genuinely better here.) |
| Graceful shutdown | Not tested | Did not interrupt mid-inference. TODO. |
| Multi-model serving | **D** | One model per server instance. Multiple models = multiple containers. |
| Quantization options | **A** | Full GGUF quant spectrum available externally; you pick your file. |
| Chat template handling | **A** | `--jinja` on by default, picks up the model's trained template from GGUF. Tool calling works out of the box. |

### Deployment fit

| Axis | Grade | Notes |
|---|---|---|
| Official container image | **B** | GHCR, official org, but `:server` tag is floating and image labels don't self-identify llama.cpp version. Digest pinning is mandatory for reproducibility. |
| Helm chart | N/A | No official chart. Community charts exist. |
| Idle RAM | **A** | Model weights resident as expected (~2 GB for 3B Q4). No daemon overhead beyond the model. |
| CPU-only viability | **A** | Runs cleanly on CPU. 3B Q4 serves at ~15 tok/s on 20-core i9 — faster than Ollama on the same box. |
| K8s GPU integration | **B** | Build-time CUDA support; GPU image variants on GHCR. Not exercised in Phase 1. |

### Adoption signal

| Axis | Grade | Notes |
|---|---|---|
| License | **A** | MIT. |
| Commit / release cadence | **A** | Extremely active. 5 builds on eval day alone. |
| Maintainership | **A** | Large contributor base, ggml-org stewardship. |
| Breaking-change frequency | **C** | Build-numbered releases; no LTS branch; API and flag surface shifts meaningfully between builds. Pin by digest and test on upgrade. |

---

## Tool-calling probe results (5/5)

All four tools correctly invoked with structured `tool_calls`:

- PASS: `query_prometheus` for metric trend
- PASS: `fetch_logs` for error investigation
- PASS: `get_runbook` by alert name
- **PASS: `create_ticket`** (Ollama's failure case — same model, same quant — passes here)
- PASS: `fetch_logs` with required `label_selector` arg

The difference vs Ollama is attributable to `--jinja` being on by default. Qwen2.5's
chat template includes tool-call rendering instructions that jinja parses correctly;
without it, the small model occasionally emits tool-call JSON in the `content` field
as plain text. That's a runtime-level architectural choice, not a model issue.

## Raw latency numbers

```
Endpoint: http://localhost:8081  Model: qwen2.5-3b-instruct-q4_k_m.gguf  Runs: 10 (+ 1 warmup)
Time to first token:  p50=0.08s  p95=0.33s  min=0.07s  max=0.51s
Total response time:  p50=4.52s  p95=6.02s  min=3.60s  max=6.53s
Output tokens:        p50=65    p95=84    mean=67
```

Cold load: ~4s to first-ready state (faster than Ollama's ~8.4s; single-model server
doesn't pay the registry-resolve overhead). Steady-state faster across the board.

## Head-to-head with Ollama (same model, CPU, quant)

| Axis | Ollama 0.21.0 | llama.cpp b8833 | Winner |
|---|---|---|---|
| Context default | 2048 (clamped) | 32768 (native) | **llama.cpp** |
| Tool calling | 4/5 | 5/5 | **llama.cpp** |
| TTFT p95 | 0.28s | 0.33s | Ollama (marginal) |
| Total p95 | 9.77s | 6.02s | **llama.cpp** |
| Concurrency 5x speedup | 3.77x | 4.25x | **llama.cpp** |
| Built-in auth | none | `--api-key` | **llama.cpp** |
| Built-in metrics | none | `--metrics` | **llama.cpp** |
| Health endpoint | no | yes | **llama.cpp** |
| DNS rebinding block | yes | **no** | **Ollama** |
| Live prompt leak surface | none | **/slots on default** | **Ollama** |
| Image version self-id | yes | no | **Ollama** |
| Multi-model serving | automatic LRU | one-per-server | **Ollama** |

llama.cpp takes the engine fight. Ollama takes the "out-of-the-box default posture"
fight on two specific axes (browser attack surface, data leakage). Both lose the
"is the default safe" question, but they lose differently — and those differences
matter for tenant deployment design.

## Narrative

llama.cpp is the engine. Ollama is the engine wrapped in a product. On a CPU box
running a 3B Q4 model, llama.cpp is 35% faster end-to-end, passes all five tool-call
cases instead of four, honors the model's native 32k context instead of silently
stepping down to 2k, and exposes `--api-key`, `--metrics`, `/health` as built-ins
rather than as "somebody else's problem." If the question is "which runtime treats
the server itself as a real piece of infrastructure," the answer is llama.cpp.

Then you meet the defaults. `/slots` is on — unauthenticated, serving live session
state. Origin-header rebinding is off — a malicious webpage on the same LAN can read
and drive your model through the browser. The image has no llama.cpp version in its
OCI labels, so "what am I running?" requires hitting the running server. The `:server`
tag floats. The release cadence is five builds a day. There's no LTS.

That combination — strong engine, strong hardening levers, weak defaults, weak release
discipline — is actually *better* raw material for the lab than Ollama's "ship a
product, punt on security" profile. The hardening story is smaller and more legible:
flag `--api-key`, flag `--no-slots`, flag `--metrics`, drop to non-root in a custom
image, pin by digest, Kyverno-admission-check all of the above. No reverse proxy,
no sidecar exporter, no architectural workaround. That's a cleaner before/after
demonstration than Ollama's "build a security appliance around it."

## Would I run this in a customer tenant?

**Yes, and more enthusiastically than Ollama.** The hardening surface is concentrated
in flags and image customization, not in surrounding infrastructure. Build a custom
image that runs as a non-root UID, bakes `--api-key-file /run/secrets/api-key`,
`--no-slots`, `--metrics`, `--host 127.0.0.1` (for in-pod networking through a sidecar)
or a unix socket, and pins the llama.cpp build by digest. Wrap it in a Kyverno policy
that refuses admission unless those flags are present and the image matches the
approved digest. Add a scheduled job to rebuild against a known-good llama.cpp commit
on a review cadence, since there's no LTS to pin to.

The catch is the one-model-per-server limit. For a single-agent-workload lab this is
fine; for a multi-tenant agent platform serving diverse models, you end up running N
llama.cpp pods vs one Ollama pod. That's a tradeoff the deployment chapter can make
honestly.

## TODOs (not blocking)

- Graceful shutdown test (`SIGTERM` mid-inference)
- Verify `--api-key` enforces 401 on missing/bad key
- Verify `--no-slots` closes `/slots` (expect 404)
- Cosign signature status for the GHCR image
- `--jinja` off vs on A/B — quantify the tool-call reliability delta
- Phase 2 GPU rerun with a 7B model
