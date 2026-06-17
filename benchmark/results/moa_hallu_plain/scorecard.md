# Does aggregation reduce hallucinations?

- Panel: meta-llama/llama-3.3-70b-instruct, qwen/qwen3-235b-a22b-2507, deepseek/deepseek-v3.2, mistralai/mistral-large-2512
- Single baseline: `meta-llama/llama-3.3-70b-instruct` · Grader: `google/gemini-2.5-pro`
- Items: 15 · Contestants: moa

## SimpleQA — obscure facts (idiosyncratic confabulation; consensus *should* help)

| contestant | correct | **hallucinated** | abstained | avg calls |
|---|--:|--:|--:|--:|
| moa | 20.0% | **73.3%** | 6.7% | 13.9 |
