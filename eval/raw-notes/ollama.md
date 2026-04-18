# Raw notes — Ollama v0.21.0

Date: 2026-04-17
Environment: WSL2 Ubuntu on Windows, Docker 29.1.3, i9-12900H, 31 GB RAM, CPU-only (no GPU passthrough configured)
Image: `ollama/ollama:0.21.0` — digest `sha256:d3d553bdfbcc7f55dd5ddf42c4cbe3a927aa9bb1802710d35e94656ca5aea02b`

Rule: capture reactions as they happen. No sanitizing.

## Setup command (as documented)

```bash
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama-eval ollama/ollama:0.21.0
```

This is literally Ollama's recommended install command minus `--gpus=all`. Matches what a busy engineer would run.

## Default-state findings

### Footgun 1 — Published to all host interfaces by default
```
PORTS: 0.0.0.0:11434->11434/tcp, [::]:11434->11434/tcp
```
The `-p 11434:11434` form publishes to all interfaces. Documented command does not use `-p 127.0.0.1:11434:11434`. On WSL2 this is bounded by the Windows host's firewall; on a bare Linux host on a LAN, this is immediately reachable from the network. Combined with no auth: trivially exploited.

### Footgun 2 — Container runs as root
```
uid=0(root) gid=0(root) groups=0(root)
```
No `USER` directive in the image. A privilege escalation from inside the container lands directly on UID 0. For a runtime that processes untrusted model files from public registries, this is not defensible.

### Footgun 3 — Container internally binds 0.0.0.0
```
OLLAMA_HOST=0.0.0.0:11434
```
Even if a user is careful with `-p 127.0.0.1:11434:11434`, the server inside the container is listening on every interface. Any other container in the same network, any sidecar, any host-network namespace neighbor can reach it. This is an image-level decision, not a deployment-level one.

### Footgun 4 — No authentication, anywhere
The critical advisory GHSA-f6mr-38g8-39rg describes this exactly: "The platform exposes multiple API endpoints without requiring authentication, enabling remote attackers to perform unauthorized model management operations." Officially "vulnerable range: ≤ 0.12.3" but v0.21.0 still ships zero auth by default. Verified:

```
GET  /api/tags     → 200 (model list)
GET  /api/ps       → 200 (running models)
GET  /api/version  → 200 (version disclosure)
POST /api/pull     → 400 on invalid body (endpoint reachable, will execute valid calls)
DELETE /api/delete → 400 on invalid body (reachable)
POST /api/create   → 400 on invalid body (reachable)
```

The "fix" is environmental: put a reverse proxy in front. The project's position is that auth is not the runtime's job. That is a defensible engineering opinion and an indefensible default posture — most people are going to skip the reverse proxy step.

### Win 1 — Origin-based DNS rebinding protection in place
```
curl -H 'Origin: http://evil.com' http://localhost:11434/api/tags  → 403
curl -H 'Origin: http://127.0.0.1:11434' http://localhost:11434/api/tags  → 200
```
The 2024 DNS rebinding advisory (GHSA-5jx5-hqx5-2vrj, patched <0.1.29) is properly addressed. Browser-based cross-origin attacks are blocked. Non-browser clients still pass through (no Origin check), which is the correct behavior for an API — the threat is specifically browsers.

### Neutral — No CORS headers returned
Absence of `Access-Control-Allow-Origin` is correct — browsers block cross-origin reads. Combined with Origin-based rebinding check, browser-side attack surface is closed. But this is the *only* security layer working by default.

### Footgun 5 — No observability endpoint
```
GET /metrics → 404
```
No Prometheus-format metrics endpoint. No way to know what's happening in production without parsing logs. For a runtime that's serving agent workloads with audit-trail requirements, this is a real operational gap.

### Footgun 6 — Host header not validated on non-browser requests
```
curl -H 'Host: evil.com' http://localhost:11434/api/tags  → 200
```
No Host header enforcement for direct requests. Fine for API clients, but means no defense-in-depth against a misconfigured proxy or DNS trick at the L7 layer. The Origin-based check handles browsers; nothing else protects against spoofed Host in non-browser contexts.

### Neutral — TLS is expected to be external
```
curl https://localhost:11434/  → connection failure
```
No TLS on the default port. All traffic is cleartext HTTP. Expected to be terminated by a reverse proxy. Consistent with the project's "you handle the front door" philosophy.

### Neutral — NVIDIA env vars baked in
```
NVIDIA_VISIBLE_DEVICES=all
NVIDIA_DRIVER_CAPABILITIES=compute,utility
```
Requests GPU access if available. No effect on CPU-only runs. Would matter more for a locked-down Kubernetes deployment where explicit device requests are preferred.

## Supply-chain observations

- Docker image tag `:latest` exists (published ~6h before `0.21.0`). Matches the typical `latest`-floats-over-release pattern. Pinning is on the user.
- Image is an official Docker Hub publication, not a third-party fork.
- Did not verify image signing — Ollama does not appear to publish Cosign signatures for the Docker Hub image (worth a follow-up check).
- 14 published GitHub advisories against `github.com/ollama/ollama`, 1 critical, 8 high, 4 medium. All have `patched_versions: none` in advisory metadata — means either "fixed by version bump past the vulnerable range" (likely) or "fixed by config" (worrying). Either way, nothing in the advisory record tells a user they're safe without cross-referencing release notes.

## Functional testing (to be filled when model pull completes)

Model: `qwen2.5:3b` (pull in progress)

- [ ] Context length probe (32k)
- [ ] Tool calling probe (structured output)
- [ ] Latency probe (p50/p95 across 10 requests)
- [ ] Concurrency probe (5 simultaneous)
- [ ] Graceful shutdown behavior
- [ ] Model swap / hot reload

## Running verdict (pre-functional)

The *runtime* is reasonable software. The *defaults* are a security appliance aimed at your foot. Everything that would make this safe — auth, localhost bind, non-root user, observability — is an exercise left to the operator, and the project's documentation doesn't push operators toward any of it.

For the lab's editorial stance ("if a competent-but-busy engineer runs the documented default, are they safe?"): **no.** That's the headline.

Whether Ollama makes it into the lab depends entirely on whether the hardening work (reverse proxy with auth, non-root user via custom image or `--user` flag, localhost-only bind, sidecar metrics exporter, Kyverno policies enforcing all of the above) is reasonable to demonstrate. Probably yes — the Kyverno-enforces-the-hardening story is its own blog post.
