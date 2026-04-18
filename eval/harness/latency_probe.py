#!/usr/bin/env python3
"""
Latency probe — measures p50/p95 for full-response and first-token latency
against an OpenAI-compatible or Ollama-native endpoint.

Usage:
    python3 latency_probe.py --endpoint http://localhost:11434 --model qwen2.5:3b
"""
import argparse
import json
import statistics
import time
import urllib.request


TRIAGE_PROMPT = """You are an on-call first-responder agent triaging an alert.

Alert name: PaymentsP95LatencyHigh
Service: payments-api
Severity: warning
Summary: p95 request latency for payments-api exceeded 800ms for the last 5 minutes.
Started: 5 minutes ago
Recent metric trend: latency rose from ~350ms baseline to 820ms p95 over ~3 minutes
Recent logs (last 2 minutes): 42 timeouts on downstream call to ledger-service, 3 circuit-breaker-open events

Based on this, in 3-4 sentences, give a probable cause hypothesis and one suggested next step.
Reply in plain text, not JSON.
"""


def stream_request_ollama(endpoint: str, model: str, prompt: str) -> dict:
    url = f"{endpoint.rstrip('/')}/api/generate"
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": {"num_predict": 200},
    }).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )

    t0 = time.perf_counter()
    t_first_token = None
    total_tokens = 0

    with urllib.request.urlopen(req) as resp:
        for line in resp:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("response"):
                if t_first_token is None:
                    t_first_token = time.perf_counter() - t0
                total_tokens += 1
            if obj.get("done"):
                t_total = time.perf_counter() - t0
                return {
                    "time_to_first_token_s": t_first_token,
                    "total_time_s": t_total,
                    "total_tokens": obj.get("eval_count", total_tokens),
                    "prompt_tokens": obj.get("prompt_eval_count", 0),
                    "eval_duration_s": obj.get("eval_duration", 0) / 1e9,
                    "prompt_eval_duration_s": obj.get("prompt_eval_duration", 0) / 1e9,
                }
    return {}


def stream_request_openai(endpoint: str, model: str, prompt: str) -> dict:
    """OpenAI-compatible streaming via /v1/chat/completions (SSE)."""
    url = f"{endpoint.rstrip('/')}/v1/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": 200,
    }).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )

    t0 = time.perf_counter()
    t_first_token = None
    total_tokens = 0
    usage = {}

    with urllib.request.urlopen(req) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                if delta.get("content"):
                    if t_first_token is None:
                        t_first_token = time.perf_counter() - t0
                    total_tokens += 1
            if obj.get("usage"):
                usage = obj["usage"]

    t_total = time.perf_counter() - t0
    return {
        "time_to_first_token_s": t_first_token,
        "total_time_s": t_total,
        "total_tokens": usage.get("completion_tokens", total_tokens),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "eval_duration_s": 0,
        "prompt_eval_duration_s": 0,
    }


def stream_request(endpoint: str, model: str, prompt: str, api: str) -> dict:
    if api == "openai":
        return stream_request_openai(endpoint, model, prompt)
    return stream_request_ollama(endpoint, model, prompt)


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    return values[f] + (values[c] - values[f]) * (k - f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:11434")
    ap.add_argument("--model", required=True)
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--warmup", type=int, default=1)
    ap.add_argument("--api", choices=["ollama", "openai"], default="ollama")
    args = ap.parse_args()

    print(f"Endpoint: {args.endpoint}  Model: {args.model}  API: {args.api}  Runs: {args.runs} (+ {args.warmup} warmup)\n")

    for i in range(args.warmup):
        print(f"  warmup {i+1}/{args.warmup}...", flush=True)
        stream_request(args.endpoint, args.model, TRIAGE_PROMPT, args.api)

    results = []
    for i in range(args.runs):
        r = stream_request(args.endpoint, args.model, TRIAGE_PROMPT, args.api)
        results.append(r)
        print(
            f"  run {i+1:2d}: first-token {r['time_to_first_token_s']:.2f}s  "
            f"total {r['total_time_s']:.2f}s  "
            f"tokens {r['total_tokens']}  "
            f"prompt_tokens {r['prompt_tokens']}"
        )

    ttft = [r["time_to_first_token_s"] for r in results if r["time_to_first_token_s"] is not None]
    total = [r["total_time_s"] for r in results]
    tokens = [r["total_tokens"] for r in results]

    print("\n=== Summary ===")
    print(f"Time to first token:  p50={percentile(ttft,50):.2f}s  p95={percentile(ttft,95):.2f}s  min={min(ttft):.2f}s  max={max(ttft):.2f}s")
    print(f"Total response time:  p50={percentile(total,50):.2f}s  p95={percentile(total,95):.2f}s  min={min(total):.2f}s  max={max(total):.2f}s")
    print(f"Output tokens:        p50={percentile(tokens,50):.0f}  p95={percentile(tokens,95):.0f}  mean={statistics.mean(tokens):.0f}")
    print(f"\nPre-filter gates (Phase 1 / CPU 3B):")
    print(f"  p95 first-token < 5s:   {'PASS' if percentile(ttft,95) < 5 else 'FAIL'}  (observed {percentile(ttft,95):.2f}s)")
    print(f"  p95 full < 30s:         {'PASS' if percentile(total,95) < 30 else 'FAIL'}  (observed {percentile(total,95):.2f}s)")


if __name__ == "__main__":
    main()
