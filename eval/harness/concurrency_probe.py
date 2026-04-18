#!/usr/bin/env python3
"""
Concurrency probe — fires N simultaneous requests and measures behavior:
were they truly concurrent, did any error, what was the p95 latency under load
compared to sequential.

Usage:
    python3 concurrency_probe.py --model qwen2.5:3b --concurrent 5
"""
import argparse
import concurrent.futures as cf
import json
import time
import urllib.request


PROMPT = "Reply with exactly one sentence describing what a circuit breaker does."


def one_request(endpoint: str, model: str, idx: int, api: str) -> dict:
    if api == "openai":
        url = f"{endpoint.rstrip('/')}/v1/chat/completions"
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
            "stream": False,
            "max_tokens": 60,
        }).encode()
    else:
        url = f"{endpoint.rstrip('/')}/api/generate"
        body = json.dumps({
            "model": model,
            "prompt": PROMPT,
            "stream": False,
            "options": {"num_predict": 60},
        }).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
        if api == "openai":
            tokens = (data.get("usage") or {}).get("completion_tokens")
        else:
            tokens = data.get("eval_count")
        return {
            "idx": idx,
            "ok": True,
            "latency_s": time.perf_counter() - t0,
            "tokens": tokens,
            "status": "ok",
        }
    except Exception as e:
        return {
            "idx": idx,
            "ok": False,
            "latency_s": time.perf_counter() - t0,
            "error": str(e),
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:11434")
    ap.add_argument("--model", required=True)
    ap.add_argument("--concurrent", type=int, default=5)
    ap.add_argument("--api", choices=["ollama", "openai"], default="ollama")
    args = ap.parse_args()

    print(f"Firing {args.concurrent} simultaneous requests to {args.endpoint}  model={args.model}  api={args.api}\n")

    t_start = time.perf_counter()
    with cf.ThreadPoolExecutor(max_workers=args.concurrent) as ex:
        futures = [ex.submit(one_request, args.endpoint, args.model, i, args.api) for i in range(args.concurrent)]
        results = [f.result() for f in cf.as_completed(futures)]
    t_end = time.perf_counter()
    wall = t_end - t_start

    results.sort(key=lambda r: r["idx"])
    for r in results:
        if r["ok"]:
            print(f"  req {r['idx']}: {r['latency_s']:.2f}s  tokens={r['tokens']}")
        else:
            print(f"  req {r['idx']}: ERROR after {r['latency_s']:.2f}s — {r['error']}")

    oks = [r for r in results if r["ok"]]
    errs = [r for r in results if not r["ok"]]
    lats = [r["latency_s"] for r in oks]

    print(f"\nWall clock for {args.concurrent} concurrent: {wall:.2f}s")
    print(f"Sum of individual latencies: {sum(lats):.2f}s")
    print(f"Speedup factor (sum / wall): {sum(lats)/wall:.2f}x  "
          f"(1.0 = fully serialized, N = fully parallel)")
    print(f"Errors: {len(errs)}/{args.concurrent}")
    if oks:
        print(f"Latency under load: min={min(lats):.2f}s  max={max(lats):.2f}s  mean={sum(lats)/len(lats):.2f}s")


if __name__ == "__main__":
    main()
