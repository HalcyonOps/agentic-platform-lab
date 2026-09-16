# Evaluation Plan — Phase 1 (CPU) and Phase 2 (GPU)

Two-phase eval, matching the charter's laptop-first posture. Demonstrating both CPU and GPU paths is the point, not an afterthought.

## Phase 1 — CPU baseline (now)

**Environment:** WSL2 Ubuntu on Windows, no GPU passthrough yet. i9-12900H / 20 cores / 31 GB RAM / 879 GB free. Docker 29 available.

**Model class:** 3B parameters, Q4 quantization. Small enough that inference latency on a 20-core CPU stays defensible. Not representative of production throughput — representative of *laptop viability*.

**Candidates (in order):**
1. **Ollama** — most popular, best defaults-story signal, containerized and CLI-native
2. **llama.cpp server (`llama-server`)** — native CPU target, transparent
3. **LocalAI** — OpenAI-compatible aggregator, worth seeing how it compares

**Deferred to Phase 2 (GPU-dependent):**
- vLLM — CPU mode exists but is not the intended target
- TGI — same

Running vLLM / TGI on CPU would produce misleading numbers. They're designed around CUDA paged-attention; CPU scores don't generalize.

## Phase 2 — GPU (later)

**Trigger:** run from a machine with a discrete GPU (one exists in the fleet, not yet scheduled for this), or a cloud VM with GPU budgeted.

**Model class:** 7B–13B parameters, Q4/Q5 quantization. Representative of realistic agent workload.

**Candidates:** All five from the rubric. CPU candidates get re-run for apples-to-apples, plus vLLM and TGI enter the picture.

**Goal:** Lab supports both CPU and GPU deployment modes. A user cloning the repo should be able to run on a laptop without a GPU and see the agent work — just slower.

## How latency gates apply across phases

The pre-filter latency gate (`p95 first-token < 5s, p95 full < 30s`) is **model-size-aware**:

| Phase | Model size | Gate |
|---|---|---|
| Phase 1 (CPU) | 3B Q4 | p95 first-token < 5s, p95 full < 30s |
| Phase 2 (GPU) | 7B Q4 | p95 first-token < 2s, p95 full < 10s |

A runtime that clears the Phase 1 gate at 3B and clears the Phase 2 gate at 7B is viable. One that fails either is not.

## First-pass execution — Ollama on CPU

1. Pull `ollama/ollama:<pinned-version>` (verify current stable before pinning; do not use `:latest`).
2. Run with default arguments. Capture:
   - Bind address default
   - Container user (root / non-root)
   - Exposed ports
   - Volume mount behavior
   - Auth posture
3. Pull model: `qwen2.5:3b-instruct` (Q4_K_M default via Ollama). Chosen for solid function-calling support at small size.
4. Run pre-filter probes in order:
   - Context length probe (32k requirement)
   - Tool calling probe (structured output test)
   - Latency probe (10 requests, measure p50/p95)
   - Concurrency probe (5 simultaneous requests, measure behavior)
5. Run security / observability / operational axes.
6. Write the narrative. Opinionated. Leads with the most interesting footgun or win.
7. Output to `eval/results/ollama.md`.

## Test harness — minimum viable first

The harness is built *during* the first run, not before. Scope creep kills eval projects.

**Minimum viable:** A Python script that takes an OpenAI-compatible endpoint URL and runs the probes. All five candidate runtimes expose OpenAI-compatible APIs, so the harness is runtime-agnostic once built.

Location: `eval/harness/` (built iteratively as needed).

Not building: a full pytest suite, CI integration, a web dashboard, or a "benchmarking framework." The harness is a lab instrument, not a product.

## Rules during the eval

- Capture *defaults*. If a flag has to be set to make the runtime safe, that's the story — don't silently fix it and forget.
- Take raw notes. Reactions matter. Sanitized post-hoc writeups lose the teardown quality.
- Track what was *not* tested. Unknowns are part of the record.
- Don't compare numbers across phases. A 3B CPU latency and a 7B GPU latency are not the same data point.

## Deliverable per runtime

A populated scorecard in `eval/results/<runtime>.md`:

1. One-line verdict (blog-headline quality)
2. Pre-filter result: PASS / FAIL (gate: reason)
3. Scorecard table
4. Narrative — two paragraphs, voice-on
5. "Would I run this in a customer tenant?" — yes / yes-with-caveats / no, plus one-line reason
