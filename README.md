# Multi-Model Debate

Query a panel of **open-weight LLMs on OpenRouter** with the same prompt, run
**debate rounds** where each model critiques the others and revises its answer, and
return the **consensus reply** once a quorum agrees — plus the full transcript.

Ships as a drop-in **Claude skill**, a **Hermes / generic-harness tool**, an
importable **Python package**, and a **CLI**. Zero runtime dependencies (Python
standard library only).

```bash
export OPENROUTER_API_KEY=sk-or-...
python -m multimodel_debate "Should a 5-person team adopt a monorepo?" --models reasoning --synthesize
```

---

## Why

A single model can be confidently wrong. Asking several *different* models the same
question and making them argue surfaces disagreement, cancels one-off mistakes, and
produces an answer no single model would give alone.

We benchmarked three approaches — a single frontier model (Claude Opus 4.8), a
**fusion** of open-weight models (parallel answers + one aggregator), and a full
**debate** to consensus. The headline:

> On objective tasks, **all three tie at 100%** — a diverse open-weight panel matches
> Opus. **Fusion ≈ debate in quality at ~half the cost**; debate's edge shows only on
> open-ended reasoning (it won the blind-judged question). The shared limitation:
> **aggregation cancels errors the models make *independently*, and is blind to ones
> they *share*** — though a one-line prompt cue can make the panel see a blind spot it
> would otherwise miss. → [full results](docs/RESULTS.md)

So: diversify the panel by lineage, default to fusion for cost, reach for debate on
hard reasoning, and never read agreement as "verified correct."

A short write-up of the findings — including the hallucination result and the
abstention/disagreement mechanism — is in **[docs/PAPER.md](docs/PAPER.md)**.

## How it works

1. **Round 0 — independent answers.** Every model answers blind to the others.
2. **Debate rounds.** Each model sees the others' answers (anonymized as Peer A/B/C),
   writes a critique, a revised answer, and votes `AGREE` / `DISAGREE`.
3. **Stop** when a quorum agrees (consensus) or the round cap is hit.
4. **Reply** = the converged answer (or a merged one with `--synthesize`).

A model that errors or returns nothing is dropped; the debate continues with ≥2.

## Features

- **Pick any models** — presets (`default` / `cheap` / `reasoning`) or exact
  OpenRouter slugs, with live model discovery (`--list-models`, `--pick`).
- **Configurable consensus** — `all` (unanimous), `majority`, a count (`2`), or a
  fraction (`2/3`).
- **Configurable rounds** and a `--synthesize` step to merge the final answers.
- **Robust** — tolerates messy model formatting; drops failed/empty models; never
  forces a false consensus.
- **Benchmark suite** — compare any model vs the consensus with code-graded and
  blind-judged tests.

## Quickstart

```bash
# 1. install (optional — gives you the `mmdebate` command)
pip install -e .

# 2. discover models (no token cost)
mmdebate --list-models deepseek

# 3. run a debate with a reasoning panel
mmdebate "Is P=NP likely to be resolved this decade?" \
  --models "deepseek/deepseek-r1-0528,qwen/qwen3-235b-a22b-2507,z-ai/glm-5" \
  --consensus majority --synthesize

# from Python
python examples/basic.py
```

See **[docs/INSTALL.md](docs/INSTALL.md)** and **[docs/MANUAL.md](docs/MANUAL.md)**.

## Install as a skill / tool

| Target | What to do |
|---|---|
| **Claude Code** | `cp -r skills/claude/multi-model-debate ~/.claude/skills/` then restart |
| **Claude.ai** | upload `skills/claude/multi-model-debate/` as a custom skill |
| **Hermes / agent harness** | use the Agent Skills dir, or register [`skills/hermes/tool.json`](skills/hermes/tool.json) → [`skills/hermes/run.py`](skills/hermes/run.py) |
| **Any Python** | `from multimodel_debate import run_debate` |

Details: [skills/hermes/SKILL.md](skills/hermes/SKILL.md), [docs/INSTALL.md](docs/INSTALL.md).

## Repository layout

```
multi-model-debate/
├── multimodel_debate/        # canonical Python package (CLI + library)
│   ├── debate.py             #   orchestrator: rounds, consensus, synthesis
│   ├── openrouter.py         #   zero-dep OpenRouter client
│   └── models.py             #   panel presets + resolution
├── skills/
│   ├── claude/multi-model-debate/   # self-contained Claude Agent Skill (SKILL.md + scripts/)
│   └── hermes/                      # generic-harness tool: SKILL.md, tool.json, run.py
├── benchmark/                # Opus-vs-consensus eval harness
│   ├── run_benchmark.py · tests.json · graders.py · judge.py
│   └── results/quick/        # committed reference scorecard
├── docs/                     # INSTALL · MANUAL · RESULTS
├── examples/basic.py
└── scripts/sync_skills.py    # vendor the package into the Claude skill (single source of truth)
```

> The package in `multimodel_debate/` is the single source of truth; the Claude
> skill carries a vendored copy of those modules so it stays self-contained. After
> editing the package, run `python scripts/sync_skills.py` to re-sync.

## Configuration

- **`OPENROUTER_API_KEY`** (required) — get one at <https://openrouter.ai/keys>.
- Default panels live in [`multimodel_debate/models.py`](multimodel_debate/models.py)
  — edit to taste. Model slugs drift; `--list-models` always reflects what's live.

## License

MIT — see [LICENSE](LICENSE).
