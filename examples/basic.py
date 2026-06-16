"""Minimal example: run a debate from Python and print the result.

    export OPENROUTER_API_KEY=sk-or-...
    python examples/basic.py
"""

from multimodel_debate import run_debate

result = run_debate(
    "A startup has 18 months of runway and an unprofitable product. "
    "Should they raise now or cut burn and grow into profitability? One clear recommendation.",
    models="default",        # try "reasoning" or a comma-separated list of slugs
    max_rounds=3,
    consensus="majority",    # "all" | "majority" | "2" | "2/3"
    synthesize=True,
    on_event=lambda m: print(m),  # live progress
)

print("\n" + "=" * 60)
print(f"status: {result['status']}  |  rounds: {result['rounds_used']}")
if result.get("agreement"):
    print(f"dissenters: {result['agreement']['disagree']}")
print("=" * 60)
print(result["consensus_reply"])
