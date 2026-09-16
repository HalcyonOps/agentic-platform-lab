# Raw notes — LocalAI v4.9.0

Date: 2026-09-16
Environment: Kubuntu (native Linux, not WSL2), Docker 29.1.3, i7-12700, 20 threads, 31 GB RAM, CPU-only (no GPU passthrough configured)
Image: `localai/localai:v4.9.0` — digest `sha256:d78cd113b2bc5892d7533c1356e9c9725bb90e86a075356a63730f3d681ce4d7`

Rule: capture reactions as they happen. No sanitizing.

Note on environment: this run is on a different physical host than the Ollama/llama.cpp Phase 1 entries (WSL2 on Windows, i9-12900H). Same model class, quant, and pre-filter gates apply; absolute latency numbers are not directly comparable across hosts. Flagging this rather than silently presenting a three-way race.

## Setup command (as documented)

```bash
docker run -ti --name local-ai -p 8080:8080 localai/localai:latest
```

That's the actual README quickstart — `:latest`, no version pin, no digest. I substituted `:v4.9.0` (current latest release) for reproducibility, consistent with how Ollama and llama.cpp were pinned in this lab. **The documented default is a floating tag**, same footgun already noted for llama.cpp's `:server` tag.

I added `-v <models-dir>:/models` to supply the same `qwen2.5-3b-instruct-q4_k_m.gguf` used in the other two evals, rather than re-downloading through the gallery. This doesn't touch any of the security defaults below — it's a model-supply choice, not a hardening choice.

## Default-state findings

### Footgun 1 — Published to all host interfaces by default
```
PORTS: 0.0.0.0:8080->8080/tcp, [::]:8080->8080/tcp
```
Same pattern as Ollama and llama.cpp: the documented `-p 8080:8080` publishes to every host interface. `--address` defaults to `:8080` (all interfaces) inside the binary too — there's no env var in the quickstart that scopes it to loopback.

### Footgun 2 — Container runs as root
```
uid=0(root) gid=0(root) groups=0(root)
```
No `USER` directive. Third for three on this axis across all Phase 1 candidates.

### Footgun 3 — "no-auth single-user mode" is the literal boot message
```
INFO  stats: using in-memory ring buffer (no-auth single-user mode)
INFO  stats: fallback user wired local_user_id="59d1db5e-e78d-458d-984a-b14ccffe416c"
```
LocalAI's README advertises "Multi-user ready: API key auth, user quotas, role-based access" as a feature. True — but not the default. Zero API keys are configured out of the box (`--api-keys` is empty unless you set it), and the server says so in its own boot log. This is the most self-aware "we know this is off" message of the three runtimes, which almost makes it worse: the capability exists and ships disabled.

### Footgun 4 — Unauthenticated model management, worse than Ollama's disclosed CVE
Ollama's GHSA-f6mr-38g8-39rg is specifically about unauthenticated model pull/delete. LocalAI has the same surface and it is not a fixed/patched issue anywhere in its advisory history — it's just how the no-auth default works:

```
curl -X POST http://localhost:8080/models/apply -d '{}'
  → 200 {"uuid":"...","status":"http://localhost:8080/models/jobs/..."}

curl -X POST http://localhost:8080/models/delete/nonexistent-model-xyz
  → 200 {"uuid":"...","status":"http://localhost:8080/models/jobs/..."}
```

Both accepted with zero credentials. `/models/apply` takes a gallery/HuggingFace/OCI URI and will pull and load whatever is named — that's a remote-content-fetch primitive sitting behind no auth check by default. `/models/delete/{name}` queues an async delete job for any name, real or not (confirmed via a nonexistent model name — no 404, no auth challenge, just a job UUID).

### Footgun 5 — an unauthenticated admin agent, not just an unauthenticated API
```
INFO  LocalAI Assistant in-memory MCP server initialised tools=39 read_only=false
```
This is new relative to Ollama and llama.cpp, and it's the most interesting finding of the three evals. LocalAI ships an in-process "Assistant" — its own admin chatbot, wired to 39 internal tools, `read_only=false` — enabled by default (`--disable-local-ai-assistant` to turn it off). Separately, there's a full **Agent Pool** subsystem (`--disable-agents`, plus a dozen `--agent-pool-*` flags for vector engines, embedding models, custom actions directories, a database URL) also on by default, with its own reachable API:

```
GET  /api/agent/jobs   → 200 (empty, but reachable, no auth)
GET  /api/agent/tasks  → 200 []
POST /api/agent/jobs/execute  (exists per swagger, not exercised — didn't want to actually run an agent job against a box I don't control)
```

I did not find a public HTTP path to *talk* to the 39-tool Assistant specifically (it's wired into the WebUI's own chat modality, not obviously exposed at `/v1/mcp/chat/completions` — that endpoint is for wiring *external* MCP servers in as tools, and correctly said `"no MCP servers configured"` when queried). So the Assistant's blast radius is bounded by "whoever can reach the WebUI," not "whoever can reach the API port" — but the WebUI itself has zero auth in this configuration, so that's not much of a bound. This is exactly the shape of risk this whole lab exists to name: a tool-using agent, running with real permissions (39 tools, not read-only), reachable without so much as an API key, shipped as the friendly default.

### Footgun 6 — backend supply chain explicitly opts out of verification, by its own admission
```
WARN  installing OCI backend without signature verification
      backend=cpu-llama-cpp gallery=localai
      uri=quay.io/go-skynet/local-ai-backends:latest-cpu-llama-cpp
```
Because of the "small core, backends pulled on demand" architecture, the *inference engine itself* doesn't ship in the base image — it's a second OCI pull, from a different registry (`quay.io`), on a floating `:latest-*` tag, and the CLI tells you outright it isn't checking a signature. `--require-backend-integrity` exists (env `REQUIRE_BACKEND_INTEGRITY`) but is off by default. The May 2026 changelog advertises "keyless cosign signing of backend OCI images" as a v4.3.0 feature — the signing exists, the verification isn't wired to run automatically.

### Win 1 — Prometheus metrics on by default, not gated
```
GET /metrics → 200
# HELP api_call api calls
# TYPE api_call histogram
api_call_bucket{method="GET",otel_scope_name="github.com/mudler/LocalAI",...}
```
Real Prometheus histogram output, OTel-scoped, no flag required. Beats both Ollama (404, no metrics at all) and llama.cpp (501 unless `--metrics` is passed). First actual default-safe *observability* win across all three Phase 1 candidates.

### Win 2 — image self-identifies its own version
```
org.opencontainers.image.version: v4.9.0
org.opencontainers.image.revision: f7ad3f70eb5d8a0ddf80e08557f0d7df28cf032e
```
OCI labels carry the real version and git commit. Matches Ollama's behavior; better than llama.cpp's GHCR image (Ubuntu-base-only labels, version only visible once the server is already running).

### Neutral — CSRF middleware on by default
```
--disable-csrf   Disable CSRF middleware (enabled by default)
```
The only one of the three runtimes that ships a CSRF layer without a flag. Doesn't do much for a headless API client (CSRF matters for the WebUI/cookie-auth path more than for bearer-token API calls), but it's still a default the other two don't have at all.

### Neutral — no DNS-rebinding / Origin check
```
curl -H 'Origin: http://evil.com' http://localhost:8080/v1/models  → 200
```
Same gap as llama.cpp. Ollama is the only one of the three that blocks this by default.

### Neutral — raw GGUF drop-in is not enough; a model needs a declarative YAML
Dropping `qwen2.5-3b-instruct-q4_k_m.gguf` into the mounted `/models` directory produced `{"object":"list","data":[]}` from `/v1/models` — nothing auto-registered. LocalAI requires a model definition file (`name`, `backend`, `parameters.model`, etc.) next to the weights before it'll serve anything. This is the opposite of both Ollama (`ollama pull` handles it) and llama.cpp (`-m path/to.gguf` on the command line, no separate config file). Once the YAML existed, the referenced backend also had to be resolved to the right on-disk name — my first attempt (`backend: llama-cpp`) 500'd with `backend not found: llama-cpp` because the installed capability directory auto-named itself `cpu-llama-cpp`. Not a security finding, just a rougher path to "hello world" than the other two — worth naming since the rubric explicitly grades operational friction, not just security.

### Neutral — TLS is expected to be external
```
curl -k https://localhost:8080/  → connection refused
```
Same posture as Ollama and llama.cpp. Consistent across all three; not a differentiator.

## Functional testing

Model: `qwen2.5-3b-instruct-q4_k_m` (same GGUF file used for Ollama/llama.cpp, loaded via a hand-written model YAML: `backend: cpu-llama-cpp`, `context_size: 32768`)

- [x] Tool calling probe (structured output) — 5/5
- [x] Latency probe (p50/p95 across 10 requests)
- [x] Concurrency probe (5 simultaneous)
- [ ] Graceful shutdown behavior — not tested (same TODO as the other two entries)
- [ ] Model swap / hot reload — not tested
- [ ] Context-length stress test at the full 32k — not tested; the pre-filter gate is satisfied by "accepted the config and served coherent completions," which is the same evidentiary bar the other two entries used, not an actual 32k-token round trip

One data-quality note: the latency probe's OpenAI-compat path reported `prompt_tokens: 0` on every run. LocalAI's streaming `usage` block appears to not populate prompt-token counts mid-stream the way llama.cpp's does — completion token counts came through fine, prompt tokens didn't. Logged as an observability gap, not a functional failure.

## Running verdict (pre-functional, matches post-functional)

Same headline shape as the other two: capable engine, unsafe-by-default posture. What's different here is *what* is unsafe by default — it's not just "the inference API has no auth," it's "the inference API, the model-management API, and an agent subsystem with 39 admin tools all have no auth, and the project's own boot log says so in plain English." For a lab whose whole thesis is "agents need scoped, audited, non-default-trust infrastructure," LocalAI is the most on-the-nose example of the problem statement of the three candidates evaluated so far.
