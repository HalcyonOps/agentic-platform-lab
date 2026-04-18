# eval/models

Model weights land here at runtime. They are **not** committed — this directory is gitignored for `*.gguf`, `*.bin`, `*.safetensors`.

## Phase 1 (CPU) — standard test model

Drop this file in place before running any probe:

**`qwen2.5-3b-instruct-q4_k_m.gguf`** (~1.9 GB)

Source: [bartowski/Qwen2.5-3B-Instruct-GGUF](https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF) on HuggingFace. Pick the `Q4_K_M` variant for apples-to-apples comparison across runtimes.

```bash
curl -LO https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf
mv Qwen2.5-3B-Instruct-Q4_K_M.gguf qwen2.5-3b-instruct-q4_k_m.gguf
```

(Rename to lowercase for consistency with how llama.cpp reports it in `/v1/models`.)

## Phase 2 (GPU) — standard test model

To be finalized. Likely a 7B Q4 Qwen or Llama variant. Decision lands in `eval/EVAL_PLAN.md` when Phase 2 starts.

## Why bring-your-own

Model weights are large, per-runtime licensing varies, and the supply chain matters. Pinning a specific GGUF file hash in-repo via `.gitattributes` or Git LFS would bloat the repo and obscure what's actually being tested. The rubric in `../../EVAL_RUBRIC.md` assumes you fetch the same file, verify its SHA256, and keep that provenance alongside your own test results.
