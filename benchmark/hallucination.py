#!/usr/bin/env python3
"""Does multi-model aggregation reduce hallucinations?

Compares four ways of answering real hallucination-benchmark questions and reports,
per source, the rate of correct / hallucinated (incorrect) / abstained ("I don't
know") answers:

  - single  : one open-weight model alone (the panel's lead) — the baseline.
  - fusion  : panel answers independently, one aggregator fuses them.
  - debate  : full debate to consensus, then synthesize.
  - opus    : anthropic/claude-opus-4.8, one call — frontier reference.

Hypothesis (from docs/RESULTS.md): aggregation should cut *idiosyncratic*
confabulation (SimpleQA — obscure facts) but NOT *shared* misconceptions
(TruthfulQA), because consensus only cancels errors models make independently.

    export OPENROUTER_API_KEY=sk-or-...
    python fetch_hallu.py --per-source 20      # build hallu_tests.json first
    python hallucination.py --out results/hallu
"""

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "..", "multimodel_debate")
sys.path.insert(0, PKG)
sys.path.insert(0, HERE)

import openrouter  # noqa: E402
from debate import run_debate  # noqa: E402
import hallu_grader  # noqa: E402

# A fast (non-reasoning) panel: factual recall doesn't need long chains of thought,
# and this keeps the run tractable across dozens of questions.
PANEL = [
    "meta-llama/llama-3.3-70b-instruct",
    "qwen/qwen3-235b-a22b-2507",
    "deepseek/deepseek-v3.2",
    "mistralai/mistral-large-2512",
]
SINGLE = PANEL[0]
OPUS = "anthropic/claude-opus-4.8"
GRADER = "google/gemini-2.5-pro"
MAX_TOKENS = 1024

# Applied uniformly to every contestant so abstention is an option for all of them —
# the point is to see whether aggregation trades confabulation for honest "I don't know".
ANSWER_INSTRUCTION = (
    "Answer the question concisely. If you are not confident of the correct answer, "
    "reply exactly 'I don't know' rather than guessing."
)


def _prompt(q):
    return f"{q}\n\n{ANSWER_INSTRUCTION}"


def answer_single(model, q):
    return openrouter.chat(model, [{"role": "user", "content": _prompt(q)}], max_tokens=MAX_TOKENS)


def answer_panel(q, mode, allow_abstain=False):
    res = run_debate(
        _prompt(q),
        models=PANEL,
        mode=mode,
        max_rounds=3,
        consensus="majority",
        synthesize=True,
        allow_abstain=allow_abstain,
        max_tokens=MAX_TOKENS,
    )
    calls = len(PANEL) * (1 + res["rounds_used"]) + (1 if res["synthesized"] else 0)
    return res["consensus_reply"] or "", calls


def get_answer(contestant, q, allow_abstain=False):
    if contestant == "single":
        return answer_single(SINGLE, q), 1
    if contestant == "opus":
        return answer_single(OPUS, q), 1
    if contestant == "fusion":
        return answer_panel(q, "fusion", allow_abstain)
    if contestant == "debate":
        return answer_panel(q, "debate", allow_abstain)
    raise ValueError(contestant)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--contestants", default="single,fusion,debate,opus")
    p.add_argument("--tests", default=os.path.join(HERE, "hallu_tests.json"))
    p.add_argument("--sources", default="", help="comma-separated source filter, e.g. 'simpleqa'.")
    p.add_argument("--allow-abstain", action="store_true",
                   help="run fusion/debate with abstention-aware aggregation.")
    p.add_argument("--out", default=os.path.join(HERE, "results", "hallu"))
    args = p.parse_args()

    items = json.load(open(args.tests))["items"]
    if args.sources:
        want = {s.strip() for s in args.sources.split(",")}
        items = [it for it in items if it["source"] in want]
    contestants = [c.strip() for c in args.contestants.split(",") if c.strip()]
    log = lambda m: print(m, file=sys.stderr, flush=True)
    log(f"Hallucination eval: {len(items)} items x {len(contestants)} contestants "
        f"| allow_abstain={args.allow_abstain} | panel={PANEL}")

    rows = []
    for it in items:
        for c in contestants:
            t0 = time.time()
            try:
                ans, calls = get_answer(c, it["question"], args.allow_abstain)
            except Exception as e:  # noqa: BLE001
                ans, calls = f"(error: {e})", 0
            verdict, detail = hallu_grader.grade_factual(
                it["question"], it["gold"], it["correct"], it.get("incorrect", []), ans, GRADER
            )
            rows.append({
                "id": it["id"], "source": it["source"], "contestant": c,
                "verdict": verdict, "answer": ans, "calls": calls,
                "latency_s": round(time.time() - t0, 1),
            })
            log(f"  {it['id']:8} {c:7} -> {verdict}")

    # Aggregate: per (source, contestant) the correct / incorrect / abstained rates.
    summary = {}
    for src in sorted({r["source"] for r in rows}):
        summary[src] = {}
        for c in contestants:
            sub = [r for r in rows if r["source"] == src and r["contestant"] == c]
            n = len(sub) or 1
            summary[src][c] = {
                "n": len(sub),
                "correct_pct": round(100 * sum(r["verdict"] == "correct" for r in sub) / n, 1),
                "hallucinated_pct": round(100 * sum(r["verdict"] == "incorrect" for r in sub) / n, 1),
                "abstained_pct": round(100 * sum(r["verdict"] == "abstained" for r in sub) / n, 1),
                "avg_calls": round(sum(r["calls"] for r in sub) / n, 1),
            }

    os.makedirs(args.out, exist_ok=True)
    json.dump(rows, open(os.path.join(args.out, "rows.json"), "w"), indent=2, ensure_ascii=False)
    json.dump(summary, open(os.path.join(args.out, "summary.json"), "w"), indent=2, ensure_ascii=False)

    # Markdown scorecard: the headline number is hallucinated_pct (lower = better).
    L = ["# Does aggregation reduce hallucinations?", "",
         f"- Panel: {', '.join(PANEL)}", f"- Single baseline: `{SINGLE}` · Grader: `{GRADER}`",
         f"- Items: {len(items)} · Contestants: {', '.join(contestants)}", ""]
    src_note = {
        "simpleqa": "SimpleQA — obscure facts (idiosyncratic confabulation; consensus *should* help)",
        "truthfulqa": "TruthfulQA — common misconceptions (shared error; consensus should *not* help)",
    }
    for src, perc in summary.items():
        L += [f"## {src_note.get(src, src)}", "",
              "| contestant | correct | **hallucinated** | abstained | avg calls |",
              "|---|--:|--:|--:|--:|"]
        for c in contestants:
            s = perc[c]
            L.append(f"| {c} | {s['correct_pct']}% | **{s['hallucinated_pct']}%** | {s['abstained_pct']}% | {s['avg_calls']} |")
        L.append("")
    md = "\n".join(L)
    open(os.path.join(args.out, "scorecard.md"), "w").write(md)
    print("\n" + md)
    log(f"\nWrote {args.out}/scorecard.md")


if __name__ == "__main__":
    main()
