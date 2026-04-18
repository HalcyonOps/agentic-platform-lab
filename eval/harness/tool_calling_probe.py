#!/usr/bin/env python3
"""
Tool-calling probe — tests whether the runtime produces structured tool calls
reliably against the OpenAI-compatible /v1/chat/completions endpoint.

Uses the four tools from WORKLOAD.md to mirror the real agent surface.

Usage:
    python3 tool_calling_probe.py --endpoint http://localhost:11434 --model qwen2.5:3b
"""
import argparse
import json
import urllib.request


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_prometheus",
            "description": "Run a PromQL query against the Prometheus proxy. Read-only.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "PromQL expression"},
                    "range_start": {"type": "string", "description": "RFC3339 or 'now-30m'"},
                    "range_end": {"type": "string", "description": "RFC3339 or 'now'"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_logs",
            "description": "Fetch logs from Loki via the proxy. Label-scoped and time-bounded.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label_selector": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["label_selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_runbook",
            "description": "Retrieve a runbook by alert name.",
            "parameters": {
                "type": "object",
                "properties": {"alert_name": {"type": "string"}},
                "required": ["alert_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "Create a triage ticket. One per run.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "normal"]},
                },
                "required": ["title", "body"],
            },
        },
    },
]


SYSTEM = """You are an on-call first-responder agent. You have four tools available: query_prometheus, fetch_logs, get_runbook, create_ticket. When given an alert, decide which tool to call first. Respond only with a tool call — do not narrate."""


CASES = [
    {
        "name": "should call query_prometheus for latency trend",
        "user": "Alert fired: PaymentsP95LatencyHigh. I need the last 30 minutes of p95 latency for payments-api.",
        "expect_tool": "query_prometheus",
    },
    {
        "name": "should call fetch_logs for error investigation",
        "user": "Alert fired: payments-api is throwing 5xx. Get me the last 10 minutes of logs.",
        "expect_tool": "fetch_logs",
    },
    {
        "name": "should call get_runbook by alert name",
        "user": "Alert PaymentsP95LatencyHigh is firing. Pull the runbook.",
        "expect_tool": "get_runbook",
    },
    {
        "name": "should call create_ticket to file triage record",
        "user": "Triage complete. File a ticket titled 'Payments p95 latency spike — downstream ledger timeouts' with body 'Investigation: ...' at normal priority.",
        "expect_tool": "create_ticket",
    },
    {
        "name": "structured args: must include label_selector",
        "user": "Get me error logs from the payments service in prod for the last 5 minutes.",
        "expect_tool": "fetch_logs",
        "expect_args_include": ["label_selector"],
    },
]


def call_chat(endpoint: str, model: str, messages: list, tools: list) -> dict:
    url = f"{endpoint.rstrip('/')}/v1/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def extract_tool_call(response: dict) -> dict | None:
    try:
        msg = response["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return None
        c = calls[0]
        fn = c["function"]
        return {"name": fn["name"], "args_raw": fn.get("arguments", "{}")}
    except (KeyError, IndexError):
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default="http://localhost:11434")
    ap.add_argument("--model", required=True)
    args = ap.parse_args()

    print(f"Endpoint: {args.endpoint}  Model: {args.model}\n")

    passed = 0
    for case in CASES:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": case["user"]},
        ]
        try:
            resp = call_chat(args.endpoint, args.model, messages, TOOLS)
            tc = extract_tool_call(resp)
        except Exception as e:
            print(f"  FAIL [{case['name']}]: request error: {e}")
            continue

        if tc is None:
            content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"  FAIL [{case['name']}]: no tool_calls in response")
            print(f"    content preview: {content[:120]}")
            continue

        status = "PASS" if tc["name"] == case["expect_tool"] else "FAIL"
        if status == "PASS" and case.get("expect_args_include"):
            try:
                args_parsed = json.loads(tc["args_raw"])
                missing = [k for k in case["expect_args_include"] if k not in args_parsed]
                if missing:
                    status = "FAIL"
                    tc["missing_args"] = missing
            except json.JSONDecodeError:
                status = "FAIL"
                tc["args_parse_error"] = True

        print(f"  {status} [{case['name']}]: tool={tc['name']} expected={case['expect_tool']}")
        print(f"    args: {tc['args_raw'][:200]}")
        if status == "PASS":
            passed += 1

    print(f"\n{passed}/{len(CASES)} passed")


if __name__ == "__main__":
    main()
