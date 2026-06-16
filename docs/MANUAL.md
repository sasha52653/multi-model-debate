# Manual

Everything you can do with the multi-model debate engine: the CLI, the Python
API, model selection, consensus rules, the result schema, and the benchmark.

## Table of contents
- [How it works](#how-it-works)
- [Command line](#command-line)
- [Choosing the panel](#choosing-the-panel)
- [Rounds and the consensus rule](#rounds-and-the-consensus-rule)
- [Python API](#python-api)
- [Result schema](#result-schema)
- [Reading results honestly](#reading-results-honestly)
- [The benchmark](#the-benchmark)
- [Tuning & cost](#tuning--cost)
- [Troubleshooting](#troubleshooting)

## How it works

1. **Round 0 — independent answers.** Every model answers the prompt blind to the
   others. Lineage diversity matters: different base models disagree usefully.
2. **Debate rounds — critique, revise, vote.** Each model sees the *other* models'
   current answers (anonymized as "Peer A/B/C", so it judges content not
   reputation), writes a `CRITIQUE`, a revised `ANSWER`, and a
   `VERDICT: AGREE|DISAGREE`. AGREE means "we've converged and my answer reflects
   the shared consensus."
3. **Stop.** Consensus when a quorum votes AGREE in one round; otherwise stop at
   `--max-rounds` and return the best-effort result labeled `no_consensus`.
4. **Consensus reply.** Defaults to the converged answer of the lead (first) panel
   model; all final answers are in `final_answers`. `--synthesize` merges them into
   one canonical reply.

A model that errors, times out, or returns an empty response is dropped (recorded
in `dropped`) and the debate continues as long as ≥2 models remain.

## Command line

```bash
mmdebate "Your prompt"                      # if pip-installed
python -m multimodel_debate "Your prompt"   # without installing
cat question.md | python -m multimodel_debate -   # read prompt from stdin
```

| Flag | Meaning | Default |
|---|---|---|
| `--models` | preset (`default`/`cheap`/`reasoning`) or comma-separated slugs | `default` |
| `--list-models [SUBSTR]` | print the live OpenRouter catalogue (optional filter) and exit | — |
| `--free-only` | with `--list-models`/`--pick`, show only zero-priced models | off |
| `--pick [SUBSTR]` | interactively choose the panel by number | — |
| `--max-rounds N` | cap on debate rounds | 3 |
| `--consensus RULE` | `all` / `majority` / a count (`2`) / a fraction (`2/3`, `0.66`) | `all` |
| `--quorum F` | deprecated fractional alias for `--consensus` | — |
| `--synthesize` | merge converged answers into one canonical reply | off |
| `--temperature` / `--max-tokens` | sampling controls | 0.7 / 2048 |
| `--system` | custom system prompt for all models | — |
| `--json FILE` | write the full result dict to a file | — |
| `--full` | print the whole result dict to stdout instead of just the reply | off |
| `--quiet` | suppress stderr progress | off |

## Choosing the panel

```bash
mmdebate --list-models qwen           # browse, filtered by substring (live pricing + context)
mmdebate --list-models --free-only    # only free models
mmdebate "..." --pick deepseek        # interactive numbered picker
mmdebate "..." --models "deepseek/deepseek-r1-0528,qwen/qwen3-235b-a22b-2507,z-ai/glm-5"
```

Presets (edit [`multimodel_debate/models.py`](../multimodel_debate/models.py)):
- **`default`** — Llama 3.3 70B · Qwen3 235B · DeepSeek V3.2 · Mistral Large (diverse, balanced).
- **`cheap`** — 7–12B models for budget/high-volume runs.
- **`reasoning`** — R1 / Qwen3-thinking heavy panel for hard analytical questions.

> **Diversity beats raw strength.** Our testing (see [RESULTS.md](RESULTS.md)) found
> that a panel spanning four different labs catches errors that a panel of similar
> models shares. Optimize the panel for lineage diversity.

## Rounds and the consensus rule

```bash
mmdebate "..." --max-rounds 4 --consensus all        # unanimous
mmdebate "..." --consensus majority                  # more than half
mmdebate "..." --consensus 2                          # a fixed count, "2 of N"
mmdebate "..." --consensus 2/3                         # a fraction
```

The rule's floor is always 2 (one model can't be a consensus), and counts/fractions
are clamped to the models still live, so "3 of 4" still resolves if one drops out.

- Use **`all`** for correctness-critical, verifiable questions.
- Use **`majority`** or **`2/3`** for subjective/estimation questions where one
  holdout is expected and shouldn't block a result. (A strict `all` can report
  `no_consensus` even when the panel substantively agrees but one model is
  conservatively calibrated about voting AGREE.)

## Python API

```python
from multimodel_debate import run_debate, list_models

result = run_debate(
    prompt="Your question",
    models="reasoning",        # preset, comma string, or list of slugs
    max_rounds=3,
    consensus="majority",      # "all" | "majority" | "2" | "2/3" | 0.66
    temperature=0.7,
    max_tokens=2048,
    system=None,
    synthesize=True,
    on_event=print,            # progress callback(str)
)
print(result["consensus_reply"])

# discovery
models = list_models(query="kimi", free_only=False)
```

`run_debate` never raises for a single model failure (it drops the model). It raises
`ValueError` only for <2 models and `OpenRouterError` only if the API key is missing.

## Result schema

```jsonc
{
  "status": "consensus" | "no_consensus" | "error",
  "rounds_used": 2,
  "consensus_rule": "majority",
  "panel": ["...", "..."],            // requested panel
  "live_models": ["..."],             // survived to the end
  "dropped": { "model": "reason" },   // errors or "empty response"
  "agreement": { "round": 2, "agree": [...], "disagree": [...], "needed": 3 },
  "consensus_reply": "the final answer",
  "lead_model": "...",
  "final_answers": { "model": "its final answer" },
  "synthesized": false,
  "transcript": [
    { "round": 0, "answers": { "model": { "answer": "..." } } },
    { "round": 1, "answers": { "model": { "critique": "...", "answer": "...", "verdict": "AGREE", "label": "A" } } }
  ]
}
```

## Reading results honestly

- **`status: no_consensus`** → the round cap was hit with a live disagreement. The
  `consensus_reply` is the lead model's best answer, but treat the question as
  unresolved and look at `agreement.disagree`.
- **Unanimous agreement is not verification.** It means no panelist objected. When
  all models share a blind spot, the debate reinforces it — see [RESULTS.md](RESULTS.md).
- The most valuable signal a debate produces is often the *disagreement*, not the
  consensus. Persistent dissent means the question is genuinely uncertain.

## The benchmark

[`benchmark/`](../benchmark) compares a single frontier model (Opus) against the
open-weight consensus, grading objective tests programmatically and subjective ones
with a blind neutral judge.

```bash
export OPENROUTER_API_KEY=sk-or-...
cd benchmark

python run_benchmark.py                              # full battery, 3 repeats
python run_benchmark.py --tests rcount,roman --repeats 1   # quick subset
python run_benchmark.py --panel "qwen/qwen3-235b-a22b-2507,deepseek/deepseek-r1-0528" --out results/myrun
```

It writes `scorecard.md`, `scorecard.json`, and `rows.json` to the `--out` dir.
Add tests by editing [`tests.json`](../benchmark/tests.json); grader types are in
[`graders.py`](../benchmark/graders.py) (`numeric`, `contains_all/any`,
`rejects_premise`, `checker`, `code`, and `judge`).

> The consensus panel is **slow** (reasoning models × rounds → minutes per test).
> Run the full battery in the background.

## Tuning & cost

- **Rounds:** rarely help past 3–4; if not converged by then, the disagreement is real.
- **Temperature:** ~0.7 keeps round-0 answers diverse; lower (~0.3) for tighter convergence.
- **Cost:** ≈ `panel_size × (1 + rounds_used)` calls (+1 if `--synthesize`). The
  `cheap` preset is ~10× cheaper for iterating on prompts.
- **Latency:** ≈ the slowest model per round (calls run in parallel), so adding
  models costs tokens but little wall-clock — *unless* they're slow reasoning models.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `OPENROUTER_API_KEY is not set` | `export OPENROUTER_API_KEY=sk-or-...` |
| `HTTP 404` on a slug | the slug drifted; run `--list-models` and update it |
| A model in `dropped` with "empty response" | thinking model spent its budget; raise `--max-tokens` |
| `no_consensus` on a subjective question | loosen `--consensus` to `majority` or `2/3` |
| Claude skill doesn't trigger | restart Claude Code so it reloads the skills directory |
