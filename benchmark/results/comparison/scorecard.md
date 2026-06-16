# Frontier model vs open-weight aggregation — benchmark

- **Contestants:** `opus`, `fusion`, `debate`
- **opus:** `anthropic/claude-opus-4.8` (1 call) · **panel (fusion/debate):** `qwen/qwen3-235b-a22b-2507`, `deepseek/deepseek-r1-0528`, `moonshotai/kimi-k2.5`, `z-ai/glm-5`
- **fusion** = parallel answers + 1 aggregator (0 debate rounds) · **debate** = full debate to majority + synthesize
- **Judge:** `google/gemini-2.5-pro`  |  **Repeats:** 1

## Per-category (objective pass rate)

| Category | n | opus | fusion | debate |
|---|--:|--:|--:|--:|
| counting-gotcha | 1 | 100% | 100% | 100% |
| false-premise | 1 | 100% | 100% | 100% |
| arithmetic-reasoning | 1 | 100% | 100% | 100% |
| factual-recall | 2 | 100% | 100% | 100% |
| code-correctness | 1 | 100% | 100% | 100% |
| code-correlated-blindspot | 1 | 100% | 100% | 100% |
| constraint-following | 1 | 100% | 100% | 100% |
| long-context-faithfulness | 1 | 100% | 100% | 100% |

## Judged categories (blind judge wins)

| Category | opus | fusion | debate | tie |
|---|:-:|:-:|:-:|:-:|
| domain-reasoning | 0 | 0 | 1 | 0 |

## Overall

- **Objective pass rate** (9 graded runs/contestant): **opus** 100% · **fusion** 100% · **debate** 100%
- **Blind judge wins:** opus 0 · fusion 0 · debate 1 · tie 0
- **Avg latency:** opus ~5.3s · fusion ~66.2s · debate ~114.3s
- **Avg model calls:** opus ~1.0 · fusion ~5.0 · debate ~9.0