# Integration reference

How to embed the multi-model debate engine in other harnesses (Hermes, agent
loops, MCP servers, cron jobs) and the exact shape of what it returns.

## Python API

```python
from debate import run_debate   # if scripts/ is on sys.path
# or: from multi_model_debate.scripts.debate import run_debate

# For cheap single-pass aggregation instead of debate, use run_fusion (see below).

result = run_debate(
    prompt="Your question here",
    models="default",          # preset name, comma string, or list of slugs
    mode="debate",            # "debate" (default) | "fusion"
    max_rounds=3,              # debate rounds after the independent round
    consensus="all",          # "all" | "majority" | a count (2) | a fraction ("2/3", 0.66)
    aggregator=None,          # model that writes the final answer (default: lead panel model)
    temperature=0.7,
    max_tokens=2048,
    system=None,              # optional custom system prompt for all models
    synthesize=False,         # merge converged answers into one canonical reply
    on_event=print,           # progress callback(str); use logging in production
)

print(result["consensus_reply"])
```

`consensus` accepts the same forms as the `--consensus` CLI flag. The floor is
always 2 models, and counts/fractions are clamped to the models still live.
(`quorum=<float>` is kept as a deprecated alias that overrides `consensus`.)

### Fusion mode (cheaper alternative to debate)

```python
from debate import run_fusion
# parallel independent answers + one aggregator, no debate rounds
result = run_fusion("Your question", models="reasoning", aggregator="deepseek/deepseek-v3.2")
print(result["consensus_reply"])     # result["status"] == "fusion", rounds_used == 0
```
Equivalent to `run_debate(..., mode="fusion")`. ~half the calls/latency of debate and
matches it on objective tasks in our benchmark; debate's edge is open-ended reasoning.

### Discovering models

```python
import openrouter
models = openrouter.list_models(query="qwen", free_only=False)
# -> [{"id","name","context","prompt_price","completion_price","is_free"}, ...]
panel = [m["id"] for m in models if m["context"] and m["context"] >= 128_000][:4]
result = run_debate("...", models=panel, consensus="majority")
```

`run_debate` never blocks on the network beyond per-call timeouts and never raises
for a single model failure — it drops the model and continues. It only raises
`ValueError` if you pass fewer than 2 models, and `OpenRouterError` only if the
API key is missing.

## Result schema

```jsonc
{
  "status": "consensus" | "no_consensus" | "fusion" | "error",
  "mode": "debate" | "fusion",
  "rounds_used": 2,                      // debate rounds actually run
  "consensus_rule": "all",               // the stop rule as given ("all"/"majority"/"2"/"2/3"...)
  "panel": ["meta-llama/...", "qwen/...", ...],   // requested panel
  "live_models": ["meta-llama/...", ...],         // survived to the end
  "dropped": { "some/model": "HTTP 429: ..." },   // model -> error or "empty response"
  "agreement": {                          // verdicts in the deciding round (or last)
    "round": 2,
    "agree":    ["meta-llama/...", "qwen/..."],
    "disagree": ["mistralai/..."],
    "needed": 3                          // AGREE count required that round
  },
  "consensus_reply": "the final answer string",   // lead model's answer, or merged if synthesize
  "lead_model": "meta-llama/...",
  "final_answers": { "model": "its final answer", ... },
  "synthesized": false,
  "transcript": [
    { "round": 0, "answers": { "model": { "answer": "..." } } },
    { "round": 1, "answers": {
        "model": { "critique": "...", "answer": "...", "verdict": "AGREE", "label": "A" }
    } }
  ]
}
```

Always check `status`. `no_consensus` means the round cap was hit with a live
disagreement — the `consensus_reply` is the lead model's best answer but you
should treat the question as unresolved and inspect `agreement.disagree`.

## CLI as a subprocess

Any non-Python harness can shell out and parse JSON from a file:

```bash
python scripts/debate.py "$PROMPT" --quorum 0.75 --max-rounds 3 \
  --json /tmp/debate.json --quiet
# consensus reply is on stdout; full structured result is in /tmp/debate.json
```

`--quiet` silences stderr progress; `--full` prints the whole result dict to
stdout instead of just the reply.

## Hermes / agent-loop pattern

Expose it as a single tool the agent can call when it wants a second (third,
fourth) opinion:

```python
def multi_model_consensus(question: str, panel: str = "default") -> dict:
    from debate import run_debate
    r = run_debate(question, models=panel, max_rounds=3, quorum=0.75)
    return {
        "answer": r["consensus_reply"],
        "agreed": r["status"] == "consensus",
        "dissent": r["agreement"]["disagree"] if r.get("agreement") else [],
    }
```

Good triggers for the agent to invoke it: high-stakes decisions, factual claims it
wants cross-checked, or anywhere a single model's confidence shouldn't be trusted.

## MCP server pattern

Wrap `run_debate` as one MCP tool named e.g. `debate_to_consensus` taking
`{prompt, panel?, max_rounds?, quorum?, synthesize?}` and returning the result
dict. Because the engine is stdlib-only, the MCP server has no extra deps beyond
your MCP framework.

## Cron / batch pattern

For unattended runs, set `quiet`/structured logging and always persist the full
result so a `no_consensus` outcome is auditable later:

```bash
python scripts/debate.py --prompt-file /path/q.txt --json /var/log/debate-$(date +%s).json --quiet
```

## Cost & latency model

- Calls per run ≈ `panel_size × (1 + rounds_used)` (+1 if `synthesize`).
- Latency per round ≈ the slowest model in the panel (calls run in parallel via a
  thread pool), so adding models costs tokens but little wall-clock time.
- Use the `cheap` preset while iterating on prompts, then switch to `default` or
  `reasoning` for the real run.
