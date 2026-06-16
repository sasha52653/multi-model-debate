# Opus vs open-weight consensus — benchmark

- **Opus:** `anthropic/claude-opus-4.8` (1 call/question)
- **Consensus panel:** `qwen/qwen3-235b-a22b-2507`, `deepseek/deepseek-r1-0528`, `moonshotai/kimi-k2.5`, `z-ai/glm-5`
- **Judge (subjective):** `google/gemini-2.5-pro`
- **Repeats per test:** 1  |  **Consensus rule:** majority

## Per-category

| Category | n | Opus pass | Consensus pass | Judge (O/C/T) | Opus lat | Cons lat | Cons calls |
|---|--:|--:|--:|:--:|--:|--:|--:|
| counting-gotcha | 1 | 100% | 100% | — | 2.0s | 115.6s | 9.0 |
| false-premise | 1 | 100% | 100% | — | 3.4s | 71.1s | 9.0 |
| arithmetic-reasoning | 1 | 100% | 100% | — | 1.8s | 76.0s | 9.0 |
| factual-recall | 2 | 100% | 100% | — | 3.8s | 38.5s | 9.0 |
| code-correctness | 1 | 100% | 100% | — | 5.6s | 229.3s | 9.0 |
| code-correlated-blindspot | 1 | 100% | 0% | — | 3.1s | 1000.4s | 13.0 |
| constraint-following | 1 | 100% | 100% | — | 3.0s | 407.8s | 13.0 |
| long-context-faithfulness | 1 | 100% | 100% | — | 2.5s | 29.8s | 9.0 |
| domain-reasoning | 1 | — | — | 0/1/0 | 21.6s | 509.3s | 13.0 |

## Overall

- **Objective pass rate** (9 graded runs): Opus **100%** vs Consensus **89%**
- **Blind judge:** Opus 0 / Consensus 1 / Tie 0
- **Cost/latency:** Opus ~5.1s & 1 call; Consensus ~251.6s & ~10.2 calls (10x Opus (1 call))