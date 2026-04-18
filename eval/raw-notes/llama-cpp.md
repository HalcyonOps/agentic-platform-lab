# Raw notes — llama.cpp server (build b8833)

Date: 2026-04-17
Environment: WSL2 Ubuntu on Windows, Docker 29.1.3, i9-12900H, 31 GB RAM, CPU-only
Image: `ghcr.io/ggml-org/llama.cpp@sha256:e25ab0c4bcbe82fc766f1683a9d889bd5a0a8c76130906cd9299a1f6d7dbbffc`
Image tag used to pull: `:server` (floating — no version semantics in the tag itself)
Model: `Qwen2.5-3B-Instruct-Q4_K_M.gguf` (bartowski build, ~1.9 GB), mounted from host volume

Rule: capture reactions as they happen. No sanitizing.

## Setup command

```bash
docker run -d --name llamacpp-eval -p 8081:8080 \
  -v "$PWD/models:/models" \
  ghcr.io/ggml-org/llama.cpp@sha256:e25ab0c4... \
  -m /models/qwen2.5-3b-instruct-q4_k_m.gguf
```

No `--gpus`. CPU-only parity with Ollama run.

Note the difference in model distribution workflow: Ollama pulls via its own registry
(`ollama pull`); llama.cpp bring-your-own-GGUF, grabbed directly from HuggingFace. For a
tenant-controlled deployment this is actually a *feature* — the model supply chain stays
inside whatever artifact registry the cluster already trusts. No extra network dependency
to vet.

## Default-state findings

### Win 1 — Native context window honored by default
```
n_ctx = 32768 (from model's trained context)
```
Unlike Ollama's silent clamp to `num_ctx=2048`, llama.cpp picks up the model's trained
context length from the GGUF metadata and uses it. First-order defaults-matter point:
a 32k model actually serves 32k context. No footgun.

### Win 2 — Jinja chat templating enabled by default → tool calling works out of the box
```
--jinja, --no-jinja  (default: enabled)
```
Tool-calling probe: **5/5** passed without any flag tuning. The jinja template engine
correctly renders the tool-use portion of Qwen2.5's chat template, and `tool_calls`
lands in the `message` object as structured JSON. Same model, same quant — Ollama
got 4/5 because one case's tool-call JSON ended up in `content` as plain text.

### Win 3 — Auth is a first-class flag
```
--api-key KEY             API key to use for authentication
--api-key-file FNAME      path to file containing API keys
```
llama.cpp has a built-in bearer-token check. Not enabled by default (same as Ollama in
practice), but the capability is *in the server*, not delegated to a reverse proxy.
Hardening takes one flag instead of a sidecar.

### Win 4 — Prometheus metrics exist, just opt-in
```
--metrics    enable prometheus compatible metrics endpoint (default: disabled)
```
Contrast with Ollama, where `/metrics` returns 404 and nothing you can configure will
change that. llama.cpp has the feature, just guards it behind a flag. Better posture
for an operator who wants observability: one flag vs. building a sidecar exporter.

### Win 5 — `/health` endpoint
```
GET /health → {"status":"ok"}
```
Useful for K8s liveness/readiness probes. Ollama has no equivalent.

### Footgun 1 — `/slots` endpoint exposed by default
```
GET /slots → 200, returns full slot state including prompts and completions
```
This is a **data-leakage vector by default.** In a multi-tenant or shared-network
deployment, any reachable client can poll `/slots` and read what other users are
asking the model about. The `--no-slots` flag disables it. Should be off by default.

```
--slots, --no-slots   expose slots monitoring endpoint (default: enabled)
```

### Footgun 2 — No DNS rebinding protection
```
curl -H 'Origin: http://evil.com' http://localhost:8081/v1/models  → 200
```
This is *worse* than Ollama's posture. Ollama blocks browser-side cross-origin attacks
via Origin-header check; llama.cpp does not. For a server whose threat model
explicitly includes "someone might expose this on a LAN or local network," this is a
real gap.

### Footgun 3 — No auth by default
Same as Ollama. `/v1/models`, `/v1/chat/completions`, `/completion`, `/props`, `/slots`
all reachable without credentials. llama.cpp has `--api-key` built in, so the fix is
one flag, but the default is still wide open.

### Footgun 4 — Container runs as root
```
uid=0(root) gid=0(root) groups=0(root)
```
Same story as Ollama. No `USER` directive in the image. Privilege escalation from a
processing bug lands on UID 0 on the host namespace.

### Footgun 5 — Host header not validated
```
curl -H 'Host: evil.com' http://localhost:8081/v1/models  → 200
```
Same defense-in-depth gap as Ollama.

### Footgun 6 — Container internally binds `0.0.0.0`
```
LLAMA_ARG_HOST=0.0.0.0
```
Baked into the image. Same co-tenant / same-network reachability problem. Careful
host-port binding on the operator's side doesn't isolate the service from neighbor
containers.

### Footgun 7 — Image self-identification is missing
```
docker inspect llamacpp-eval --format '{{json .Config.Labels}}'
{"org.opencontainers.image.version":"24.04"}
```
The only OCI label is the Ubuntu base version. No `llama.cpp` version, no build
number, no git SHA, no source repo reference. For an image pulled by floating tag
(`:server`), this makes it impossible to tell after the fact *which* llama.cpp build
you're running without hitting the running server. Worse image provenance than Ollama,
which at least tags by release version.

Build number is only visible from `/v1/chat/completions` server response (`model_info`)
and from release notes on GHCR. Build number for this run: **b8833**.

### Footgun 8 — No TLS
Cleartext HTTP on 8080 inside container, 8081 on host. Same "terminate externally"
expectation as Ollama.

## Flag inventory — hardening levers available

| Lever | Flag | Default |
|---|---|---|
| Bearer-token auth | `--api-key` / `--api-key-file` | off |
| Disable slots endpoint | `--no-slots` | slots **on** |
| Enable Prometheus metrics | `--metrics` | off |
| Bind to unix socket | `--host /path/to/sock` | TCP 0.0.0.0 |
| Custom chat template | `--chat-template` / `--chat-template-file` | model-default |

Net: llama.cpp ships with *more* hardening levers than Ollama but *weaker* default
posture on browser attack surface (no rebinding check) and data leakage (slots).

## Supply chain observations

- Official image is under `ghcr.io/ggml-org/llama.cpp`, same GitHub org as source.
- Tag `:server` is a floating reference — I had to pin by digest to get reproducibility.
- Very fast release cadence — 5 builds in a single day (b8829 through b8833). Good for
  bleeding-edge kernel work; bad for an operator who wants to know they're running a
  stable audited build. No LTS or release-train model.
- **Zero GitHub security advisories** published against `ggerganov/llama.cpp` or
  `ggml-org/llama.cpp`. Interpreting this charitably: a project that isn't as widely
  deployed in sensitive contexts as Ollama yet. Interpreting it less charitably: less
  security scrutiny from the outside.
- No Cosign signatures observed on the GHCR image (worth verifying more rigorously).
- No SBOM label on the image.

## Functional results

Latency (CPU, 3B Q4, 10 runs + 1 warmup, via OpenAI-compat streaming):
```
Time to first token:  p50=0.08s  p95=0.33s  min=0.07s  max=0.51s
Total response time:  p50=4.52s  p95=6.02s  min=3.60s  max=6.53s
Output tokens:        p50=65    p95=84    mean=67
```

Concurrency (5 simultaneous):
```
Wall: 7.83s  Sum-of-latencies: 33.25s  Speedup: 4.25x  Errors: 0/5
Latency under load: min=5.63s  max=7.82s  mean=6.65s
```

Tool calling (OpenAI-compat `/v1/chat/completions` with `tools`): **5/5** passed.

## Head-to-head with Ollama (same model, same CPU, same quant)

| Axis | Ollama 0.21.0 | llama.cpp b8833 |
|---|---|---|
| Default context length | 2048 (silent clamp on 32k model) | 32768 (native) |
| Tool-calling probe | 4/5 | 5/5 |
| TTFT p50 / p95 | 0.24s / 0.28s | 0.08s / 0.33s |
| Total p50 / p95 | 6.28s / 9.77s | 4.52s / 6.02s |
| Concurrency speedup (5x) | 3.77x | 4.25x |
| Built-in auth | none | `--api-key` |
| Built-in metrics | none | `--metrics` (opt-in) |
| Health endpoint | no | yes |
| DNS rebinding protection | yes | **no** |
| Slots data-leak endpoint | n/a (no such endpoint) | **exposed by default** |
| Image version self-id | yes (tag = version) | no (floating tag, Ubuntu label only) |

llama.cpp wins on raw performance, hardening levers, and tool-call reliability.
Ollama wins on browser attack surface and image provenance. Both are wide-open by
default on auth.

## Running verdict

llama.cpp is the more serious inference engine — faster, more tool-call reliable,
more configurable, with auth and metrics hooks already in the binary. But the default
server has a live data-leakage endpoint (`/slots`) and no DNS rebinding check, so the
*default* posture is arguably worse than Ollama's even though the ceiling is higher.

For the lab's editorial frame ("does the competent-but-busy engineer get burned by
defaults?"): **yes, and the leak is more severe here** — not just unauthenticated
API access, but live visibility into other sessions' prompts.

The flip side is that the hardening story for llama.cpp is *smaller*: flip
`--api-key`, `--no-slots`, `--metrics`, drop to non-root in a custom image, and you
have a reasonable posture in one afternoon. No reverse proxy required for auth or
metrics. That's a genuine advantage for lab content — the Kyverno admission policy
becomes "enforce these flags are present," which is easier to demonstrate than
"enforce a sidecar architecture exists."

## TODOs (not blocking)

- Graceful shutdown behavior
- Verify behavior with `--api-key` set (probe the 401 path)
- Verify `--no-slots` actually closes that endpoint (expect 404)
- Cosign signature verification for GHCR image
- Phase 2 GPU rerun with 7B model
- `--jinja` off vs on A/B — quantify the tool-call reliability delta
