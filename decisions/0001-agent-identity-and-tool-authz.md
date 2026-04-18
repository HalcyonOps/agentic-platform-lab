# ADR-0001: Agent identity and tool authorization

**Status:** Accepted
**Date:** 2026-04-17
**Deciders:** the author

## Context

The lab has a hard constraint from the charter: *"identity-scoped tool use — tools know which agent run they're serving."* That's a real security claim, not a slogan, and it needs a receipt.

The workload (see `WORKLOAD.md`) is narrow: one agent concept, four tools, read-mostly with a single write path. The lab runs on Kind on a laptop first, cloud Kubernetes second. `make up` latency is part of the user experience.

Options considered:

1. **SPIFFE/SPIRE** with SVIDs for workload identity. The industry-correct answer for workload identity across heterogeneous infra. Trust bundles, automatic rotation, cryptographic attestation.
2. **Kubernetes ServiceAccount tokens + OPA at the tool proxy.** Native K8s primitives. Per-pod SA gives the identity hook; OPA policies encode the allowlists, rate limits, and scope rules.
3. **Static API keys.** Disqualified — keys are not identity. They don't satisfy the "tools know which agent *run*" requirement.
4. **Service mesh mTLS (Istio / Linkerd).** Viable, but adds a service mesh to the stack for four tool calls — disproportionate to the scope.

## Decision

Use **Kubernetes ServiceAccounts + OPA at the tool proxy.**

- Each agent role gets a ServiceAccount.
- Each agent run mounts a projected SA token with short TTL (target: 10 minutes) containing the `run_id` as a custom claim.
- Tool proxy verifies the token, extracts `run_id`, applies OPA policy (allowlists from `TOOLS.md`), and stamps `run_id` into every audit record.
- OPA policies live in a versioned directory, loaded by the proxy at startup, tested in CI.

SPIFFE/SPIRE is **deferred, not rejected.** Triggers to revisit:

- Multi-cluster or multi-cloud deployment
- Tools running outside the cluster
- Compliance regime that explicitly requires SPIFFE-compatible identity
- A real need for cryptographic workload attestation (beyond "the token came from our API server")

The proxy's token-verification layer is designed as a swap point — moving from SA JWT verification to SVID verification should be possible without changing tool code or policy.

## Consequences

**Positive**
- Native K8s primitives; no extra controllers to run, debug, or upgrade.
- Kind boots fast, `make up` stays reasonable.
- OPA policy is human-readable and easy to blog about — the blast radius of each tool is visible in a few files.
- Migration path to SPIFFE is clear; current choice doesn't paint us in.
- SA JWT + OPA is a pattern hiring managers in the federal/DoD space have actually seen. SPIFFE in a four-tool lab would look like over-engineering.

**Negative**
- SA tokens are coarser than SVIDs. Rotation is simpler but the window is less tight.
- "Why not SPIFFE?" is a question we'll get. That's fine — this ADR is the answer.
- Cryptographic attestation of workload identity is not in scope. If the threat model grows to include "the kubelet is compromised," this choice doesn't cover it.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| SA token lifetime misconfigured → long-lived credential | Use projected SA tokens with explicit `expirationSeconds: 600`, tied to expected run duration + buffer |
| OPA policy evolution becomes ad-hoc | Policies live in a versioned repo, deployed via Kustomize/Helm, tested in CI against known-good and known-bad inputs |
| Audit log gap if proxy crashes mid-call | Proxy writes audit record *before* forwarding upstream; partial records are explicitly marked `outcome: error:proxy_crash` when detected on restart |
| `run_id` spoofing by compromised agent pod | `run_id` is injected from verified token claims, never read from request body. Agent-supplied `run_id` in the request is rejected |

## References

- Charter: constraint #3 (no hand-waved security story)
- `WORKLOAD.md`: tool surface definition
- `TOOLS.md`: per-tool policy and error contract
