# Does aggregation reduce hallucinations?

- Panel: meta-llama/llama-3.3-70b-instruct, qwen/qwen3-235b-a22b-2507, deepseek/deepseek-v3.2, mistralai/mistral-large-2512
- Single baseline: `meta-llama/llama-3.3-70b-instruct` · Grader: `google/gemini-2.5-pro`
- Items: 30 · Contestants: single, fusion, debate, opus

## SimpleQA — obscure facts (idiosyncratic confabulation; consensus *should* help)

| contestant | correct | **hallucinated** | abstained | avg calls |
|---|--:|--:|--:|--:|
| single | 0.0% | **13.3%** | 86.7% | 1.0 |
| fusion | 13.3% | **80.0%** | 6.7% | 5.0 |
| debate | 26.7% | **53.3%** | 20.0% | 12.2 |
| opus | 13.3% | **0.0%** | 86.7% | 1.0 |

## TruthfulQA — common misconceptions (shared error; consensus should *not* help)

| contestant | correct | **hallucinated** | abstained | avg calls |
|---|--:|--:|--:|--:|
| single | 73.3% | **0.0%** | 26.7% | 1.0 |
| fusion | 86.7% | **0.0%** | 13.3% | 5.0 |
| debate | 100.0% | **0.0%** | 0.0% | 9.0 |
| opus | 93.3% | **0.0%** | 6.7% | 1.0 |
