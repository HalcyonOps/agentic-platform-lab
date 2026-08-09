# AGENTS.md: agentic-platform-lab

An agent workload running on tenant-controlled, security-hardened Kubernetes.
Sketch phase: charter, workload and runtime evaluation are in, the platform
build is next.

`CHARTER.md`, `WORKLOAD.md`, `TOOLS.md` and `EVAL_RUBRIC.md` are the scope
documents. `decisions/` holds ADRs. `eval/` holds the runtime evaluation.

## The thesis, because it decides what belongs here

Most agentic AI demos ship with an API key, a vendor SDK, and a handwave where
the security posture should be. This lab takes the opposite position: the
smallest honest agent workload that can be defended, on infrastructure the
tenant controls, with every piece justified against a real threat model.

The interesting work here is **admission policies, identity model, network
segmentation, observability and supply-chain discipline**. It is not prompt
engineering and it is not a notebook.

So a change that makes the agent more capable while leaving the platform story
untouched is off-thesis, however good the demo. The workload exists to have a
security posture, not the other way round.

## Constraints that are deliberate

- **CPU-only, 3B Q4 models on a laptop.** That is a constraint the lab chose, so
  the reasoning holds for someone without a GPU budget. Don't relax it to make a
  benchmark look better.
- **Tenant-controlled infrastructure**, not a vendor's. If a change requires a
  hosted service to hold the keys or run the model, it needs an ADR arguing why.
- Phase order is charter, then rubric, then evaluation, then platform. Don't
  start the platform build to avoid finishing an evaluation.

## Evaluation discipline

`EVAL_RUBRIC.md` was closed before runtimes were scored, which is the point:
the rubric cannot be adjusted to fit a result you like. Two runtimes are
evaluated, one is pending.

Record what a runtime was bad at, not only what it was good at. An evaluation
where everything passes has not been run properly.

## Claude Code specifics

`CLAUDE.md` is a symlink to this file. Codex reads only `AGENTS.md`, Claude Code
reads only `CLAUDE.md`, and neither reads the other's, so one file serves both.
`/init` will try to replace the symlink with a real file.
