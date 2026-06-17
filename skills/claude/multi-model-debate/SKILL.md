---
name: multi-model-debate
description: >
  Query several open-source LLMs on OpenRouter with the same prompt, then run
  one or more debate rounds where each model critiques the others' answers,
  revises its own, and votes AGREE/DISAGREE until the panel reaches consensus —
  returning the agreed reply plus the full transcript. Use this whenever the user
  wants a multi-model / multi-LLM answer, an "ensemble" or "panel" or "council" of
  models, models to "debate" / "argue" / "cross-examine" / "fact-check each
  other", a consensus or majority answer across models, or wants to reduce single-
  model bias/hallucination on a hard or high-stakes question. Also use when wiring
  this debate capability into another harness (Hermes, an agent loop, a cron job,
  an MCP/tool) or when the user asks for the standalone Python scripts that do it.
  Trigger even if the user names specific models (e.g. Llama, Qwen, DeepSeek,
  Mistral) and wants them compared or combined.
---

# Multi-Model Debate to Consensus

This skill orchestrates a **panel of open-weight LLMs on OpenRouter** that answer
the same prompt independently, then **debate** — each model sees the others'
answers, critiques them, revises its own, and self-reports AGREE/DISAGREE — until
a quorum agrees (consensus) or a round cap is hit. It returns the consensus reply
plus the complete transcript.

Everything lives in `scripts/` and is **pure standard library** (no pip install),
so it doubles as a standalone tool any harness can call.

## When to reach for this
- The user wants more than one model's opinion, an ensemble/panel/council, or
  models to check each other.
- A question is hard, contested, or high-stakes and single-model bias or
  hallucination is a real risk.
- The user is building it into another system (an agent, Hermes, a cron job, an
  MCP server) and wants the underlying scripts.

## Prerequisites
- `OPENROUTER_API_KEY` in the environment. If it's missing, tell the user to get
  one at https://openrouter.ai/keys and `export OPENROUTER_API_KEY=sk-or-...`.
  Do **not** invent or hardcode a key.
- Python 3.8+. No third-party packages.

## How the engine works (mental model)
1. **Round 0 — independent answers.** Every model answers blind to the others.
   Lineage diversity is the point: different base models disagree in useful ways.
2. **Debate rounds — critique, revise, vote.** Each model receives the *other*
   models' current answers, anonymized as "Peer A/B/C" (so it judges content, not
   reputation). It must output `CRITIQUE:`, a revised `ANSWER:`, and
   `VERDICT: AGREE|DISAGREE`. AGREE means "we've converged and my answer reflects
   the shared consensus."
3. **Stop condition.** Consensus when a quorum (default: unanimous) votes AGREE in
   the same round; otherwise stop at `--max-rounds` and return the best-effort
   result labeled `no_consensus`.
4. **Consensus reply.** Defaults to the converged answer of the lead (first) panel
   model — since the panel self-reported agreement, all final answers are
   substantively equivalent and all are returned in `final_answers`. Pass
   `--synthesize` to additionally merge them into one canonical reply.

The engine degrades gracefully: a model that errors (rate limit, timeout, bad
slug) is dropped with a note in `dropped`, and the debate continues as long as ≥2
models remain.

## Default usage

Run from the skill's `scripts/` directory (or reference it by absolute path):

```bash
export OPENROUTER_API_KEY=sk-or-...
python scripts/debate.py "Should a small team adopt a monorepo? Give a clear recommendation."
```

Progress prints to stderr; the final consensus reply prints to stdout.

### Choosing the panel
Three ways, in increasing specificity:

```bash
# 1. a preset
python scripts/debate.py "..." --models reasoning      # default | cheap | reasoning

# 2. exact OpenRouter slugs
python scripts/debate.py "..." --models meta-llama/llama-3.3-70b-instruct,deepseek/deepseek-v3.2

# 3. discover what's available, then pick
python scripts/debate.py --list-models qwen            # filter the catalogue by substring
python scripts/debate.py --list-models --free-only     # only zero-priced models
python scripts/debate.py "..." --pick deepseek         # interactively choose by number
```

Presets live in `scripts/models.py` (edit to change defaults):
- `default` — Llama 3.3 70B, Qwen3 235B, DeepSeek V3.2, Mistral Large (diverse).
- `cheap` — small 7–12B models for budget/high-volume runs.
- `reasoning` — R1 / Qwen3-thinking heavy panel for hard analytical questions.

### Three modes: debate / fusion / moa
```bash
python scripts/debate.py "..."                         # mode=debate (default)
python scripts/debate.py "..." --mode fusion           # parallel answers + one aggregator, no debate
python scripts/debate.py "..." --mode moa              # iterated Mixture-of-Agents to convergence
python scripts/debate.py "..." --mode fusion --aggregator deepseek/deepseek-v3.2   # pick the fuser
```
- **debate** (default) — models answer, then critique/revise *their own* position over
  rounds until a consensus quorum. Best for hard reasoning or a dissent signal.
- **fusion** — models answer independently, then one aggregator fuses them (no debate).
  ~Half the cost/latency of debate and **matches it on objective tasks** in our
  benchmarks. The cheaper default.
- **moa** — iterated Mixture-of-Agents: *every* model re-synthesizes *all* answers each
  round (each is an arbiter), repeated until the answers converge or stop changing.
  Information mixes fastest, but agreement pressure is strongest (most groupthink-prone).
  Convergence is detected by lexical similarity, which suits short/factual answers; on
  long prose it typically runs to `--max-rounds` and returns the most representative
  (medoid) answer.

In both modes, `--aggregator SLUG` chooses the model that writes the final answer
(default: the lead panel model). Add **`--allow-abstain`** to let that aggregator
reply "I don't know" when the panel's answers conflict or hedge — important for
factual questions, where forcing a committed answer turns honest uncertainty into
confident hallucination (it cut fusion's hallucination rate ~12× in testing).

### Setting the rounds and the consensus rule (debate mode)
```bash
python scripts/debate.py "..." --max-rounds 4          # cap on debate rounds (default 3)

python scripts/debate.py "..." --consensus all         # unanimous (default)
python scripts/debate.py "..." --consensus majority    # more than half
python scripts/debate.py "..." --consensus 2           # a fixed count, e.g. "2 of N"
python scripts/debate.py "..." --consensus 2/3         # a fraction (also 0.66)
```
The rule's floor is always 2 — a single model can't be a "consensus" — and counts/
fractions are clamped to the models still live, so "3 of 4" still resolves if one
model drops out. (`--quorum 0.75` is kept as a deprecated fractional alias.)

### Other flags
```bash
python scripts/debate.py "..." --synthesize            # merge converged answers into one reply
python scripts/debate.py "..." --json result.json      # save full transcript
cat question.md | python scripts/debate.py -           # pipe a long prompt
```

> Model slugs drift. `--list-models` always reflects the live catalogue; if a slug
> 404s, list current ones and update `models.py`.

## Reporting results to the user
After a run, give the user:
1. The **consensus reply** (the main answer).
2. **Status**: did they actually agree (`consensus`) or did you hit the round cap
   (`no_consensus`)? Never present `no_consensus` as settled — say where they still
   diverge, citing the dissenting model's last verdict reason.
3. Which models were on the panel and whether any were **dropped**.
4. Offer the transcript (`--json`) if they want to see how positions changed.

The most valuable thing a debate surfaces is often the *disagreement*, not just
the consensus — when models keep dissenting, that's a signal the question is
genuinely uncertain. Surface that honestly rather than forcing a tidy answer.

## Embedding in another harness
Import `run_debate` directly — it returns a JSON-serializable dict. See
[references/integration.md](references/integration.md) for the full result schema,
the Python API, and patterns for calling from agents, MCP servers, and cron jobs.

## Tuning notes
- **More rounds rarely help past 3–4.** If models haven't converged by then, they
  usually won't; the disagreement is real.
- **`--consensus all`** is strict and good for correctness-critical work; loosen
  to `majority` or `2/3` for subjective questions where one holdout is expected and
  shouldn't block a result.
- **Temperature** ~0.7 keeps round-0 answers diverse; lower it (~0.3) if you want
  tighter, more deterministic convergence.
- **Cost** scales with `panel_size × (1 + rounds)` calls (plus one if
  `--synthesize`). The `cheap` preset is ~10× cheaper for iteration.
