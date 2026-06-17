# Frontier model vs open-weight aggregation — benchmark

- **Contestants:** `moa`
- **opus:** `anthropic/claude-opus-4.8` (1 call) · **panel (fusion/debate):** `qwen/qwen3-235b-a22b-2507`, `deepseek/deepseek-r1-0528`, `moonshotai/kimi-k2.5`, `z-ai/glm-5`
- **fusion** = parallel answers + 1 aggregator (0 debate rounds) · **debate** = full debate to majority + synthesize
- **Judge:** `google/gemini-2.5-pro`  |  **Repeats:** 1

## Per-category (objective pass rate)

| Category | n | moa |
|---|--:|--:|
| counting-gotcha | 1 | 100% |
| false-premise | 1 | 100% |
| arithmetic-reasoning | 1 | 100% |
| factual-recall | 2 | 100% |
| code-correctness | 1 | 100% |
| code-correlated-blindspot | 1 | 100% |
| constraint-following | 1 | 100% |
| long-context-faithfulness | 1 | 100% |

## Judged categories (blind judge wins)

| Category | moa | tie |
|---|:-:|:-:|
| domain-reasoning | 1 | 0 |

## Overall

- **Objective pass rate** (9 graded runs/contestant): **moa** 100%
- **Blind judge wins:** moa 1 · tie 0
- **Avg latency:** moa ~182.6s
- **Avg model calls:** moa ~12.8