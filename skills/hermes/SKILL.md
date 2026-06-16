---
name: multi-model-debate
description: >
  Query several open-weight LLMs on OpenRouter with the same prompt, run debate
  rounds where each model critiques the others and revises, and return the
  consensus answer plus transcript. Use for hard, contested, or high-stakes
  questions, for a "panel"/"council"/"ensemble" of models, to have models
  cross-check or fact-check each other, or to reduce single-model bias. Also use
  when the user wants the standalone scripts or to wire this into a harness.
---

# Multi-Model Debate (Hermes / generic-harness packaging)

This is the harness-agnostic packaging of the debate engine. Two ways to wire it
in, depending on what your Hermes build supports:

## Option A — Agent Skills format
If your Hermes reads the Claude Agent Skills layout (a `SKILL.md` + bundled
`scripts/`), just use the Claude skill at
[`../claude/multi-model-debate/`](../claude/multi-model-debate) directly — it is
self-contained and identical in behavior. Copy that directory into wherever your
harness loads skills from.

## Option B — Tool / function call
For harnesses that call tools via a function schema:

1. Install the engine: `pip install multimodel-debate` (or `pip install -e .` from
   the repo root). See [`../../docs/INSTALL.md`](../../docs/INSTALL.md).
2. Register [`tool.json`](tool.json) — an OpenAI/Anthropic-style function schema
   for a `debate_to_consensus` tool.
3. Route invocations to [`run.py`](run.py): the harness serializes the arguments
   as JSON and pipes them in:
   ```bash
   echo '{"prompt":"...","panel":"reasoning","consensus":"majority"}' | python run.py --json-stdin
   ```
   `run.py` prints a JSON object: `consensus_reply`, `reached_consensus`,
   `status`, `rounds_used`, `dissenters`, `dropped`.

## Option C — direct import
Anything that can run Python can skip the indirection:
```python
from multimodel_debate import run_debate
result = run_debate("your question", models="reasoning", consensus="majority")
print(result["consensus_reply"])
```

## What the agent should know before calling
- Set `OPENROUTER_API_KEY` in the environment.
- Good triggers: high-stakes decisions, factual claims worth cross-checking, hard
  reasoning, anywhere one model's confidence shouldn't be trusted.
- **Read the result honestly:** `reached_consensus: false` means the panel still
  disagrees — surface the `dissenters`, don't present it as settled. And unanimous
  agreement means "no panelist objected," not "verified correct" — see the
  correlated-error caveat in [`../../docs/RESULTS.md`](../../docs/RESULTS.md).

Full usage, flags, and the result schema: [`../../docs/MANUAL.md`](../../docs/MANUAL.md).
