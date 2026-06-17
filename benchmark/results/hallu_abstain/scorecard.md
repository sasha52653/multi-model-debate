# Does aggregation reduce hallucinations?

- Panel: meta-llama/llama-3.3-70b-instruct, qwen/qwen3-235b-a22b-2507, deepseek/deepseek-v3.2, mistralai/mistral-large-2512
- Single baseline: `meta-llama/llama-3.3-70b-instruct` · Grader: `google/gemini-2.5-pro`
- Items: 15 · Contestants: single, fusion, debate, opus

## SimpleQA — obscure facts (idiosyncratic confabulation; consensus *should* help)

| contestant | correct | **hallucinated** | abstained | avg calls |
|---|--:|--:|--:|--:|
| single | 0.0% | **13.3%** | 86.7% | 1.0 |
| fusion | 6.7% | **6.7%** | 86.7% | 5.0 |
| debate | 26.7% | **46.7%** | 26.7% | 13.0 |
| opus | 13.3% | **0.0%** | 86.7% | 1.0 |
