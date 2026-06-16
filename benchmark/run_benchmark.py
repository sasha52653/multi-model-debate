#!/usr/bin/env python3
"""Benchmark: a frontier model vs open-weight aggregation strategies.

Three contestants answer the same prompt under the same API:
  - opus   : one call to a single frontier model (anthropic/claude-opus-4.8).
  - fusion : parallel independent answers from the panel, then ONE aggregator call
             fuses them (no debate). Implemented as a 0-round synthesize.
  - debate : the full debate engine — independent answers, then rounds of mutual
             critique/revision until a consensus quorum, then synthesize.

Objective tests are graded programmatically; subjective tests go to a blind, neutral
judge that ranks all contestants without knowing which is which. Each test repeats N
times (contestants are stochastic). We report pass rates plus a cost proxy (model
calls) and wall-clock latency per contestant.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    python run_benchmark.py                                  # all 3, all tests, 1 repeat
    python run_benchmark.py --contestants fusion,debate      # head-to-head only
    python run_benchmark.py --tests rcount,roman --repeats 1 # quick subset
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
import graders  # noqa: E402
import judge  # noqa: E402

OPUS = "anthropic/claude-opus-4.8"
PANEL = [
    "qwen/qwen3-235b-a22b-2507",
    "deepseek/deepseek-r1-0528",
    "moonshotai/kimi-k2.5",
    "z-ai/glm-5",
]
JUDGE = "google/gemini-2.5-pro"
MAX_TOKENS = 4096

# Contestant definitions. "fusion" = parallel answers + one aggregator (0 debate
# rounds, synthesize on). "debate" = full debate to majority consensus + synthesize.
CONTESTANTS = {
    "opus": {"kind": "single"},
    "fusion": {"kind": "panel", "max_rounds": 0, "consensus": "all", "synthesize": True},
    "debate": {"kind": "panel", "max_rounds": 3, "consensus": "majority", "synthesize": True},
}


def _answer(name, prompt, panel):
    """Return (answer_text, latency_s, n_calls) for one contestant; never raises."""
    spec = CONTESTANTS[name]
    t0 = time.time()
    try:
        if spec["kind"] == "single":
            ans = openrouter.chat(
                OPUS, [{"role": "user", "content": prompt}], temperature=0.7, max_tokens=MAX_TOKENS
            )
            return ans, time.time() - t0, 1
        res = run_debate(
            prompt,
            models=panel,
            max_rounds=spec["max_rounds"],
            consensus=spec["consensus"],
            synthesize=spec["synthesize"],
            max_tokens=MAX_TOKENS,
        )
        calls = len(panel) * (1 + res["rounds_used"]) + (1 if res["synthesized"] else 0)
        return res["consensus_reply"], time.time() - t0, calls
    except Exception as e:  # noqa: BLE001
        return f"({name} error: {e})", time.time() - t0, 0


def run(tests, repeats, contestants, panel, log):
    rows = []
    for t in tests:
        g = t["grader"]
        for r in range(repeats):
            log(f"  {t['id']} (rep {r + 1}/{repeats}) ...")
            answers, latency, calls = {}, {}, {}
            for name in contestants:
                a, lat, c = _answer(name, t["prompt"], panel)
                answers[name], latency[name], calls[name] = a, round(lat, 1), c

            row = {
                "id": t["id"], "category": t["category"], "repeat": r,
                "latency": latency, "calls": calls, "answers": answers,
            }
            if g["type"] == "judge":
                winner, detail = judge.multi_judge(t["prompt"], answers, g["rubric"], JUDGE, rotate=r)
                row.update(mode="judge", winner=winner, detail=detail)
                log(f"    judge -> {winner}")
            else:
                passes, details = {}, {}
                for name in contestants:
                    ok, d = graders.grade(answers[name], g)
                    passes[name], details[name] = ok, d
                row.update(mode="objective", passes=passes, details=details)
                log("    " + "  ".join(f"{n}={'PASS' if passes[n] else 'FAIL'}" for n in contestants))
            rows.append(row)
    return rows


def aggregate(rows, contestants):
    cats = {}
    for row in rows:
        cats.setdefault(row["category"], []).append(row)

    summary = {"categories": {}, "overall": {}}
    obj = {c: [] for c in contestants}
    jwins = {c: 0 for c in contestants}
    jties = 0
    lat = {c: [] for c in contestants}
    calls = {c: [] for c in contestants}

    for cat, rs in cats.items():
        c = {"n": len(rs)}
        objs = [x for x in rs if x["mode"] == "objective"]
        jus = [x for x in rs if x["mode"] == "judge"]
        if objs:
            c["objective_pass_rate"] = {
                name: round(sum(x["passes"][name] for x in objs) / len(objs), 3) for name in contestants
            }
            for name in contestants:
                obj[name] += [x["passes"][name] for x in objs]
        if jus:
            c["judge_wins"] = {name: sum(x["winner"] == name for x in jus) for name in contestants}
            c["judge_ties"] = sum(x["winner"] == "tie" for x in jus)
            for name in contestants:
                jwins[name] += c["judge_wins"][name]
            jties += c["judge_ties"]
        for name in contestants:
            lat[name] += [x["latency"][name] for x in rs]
            calls[name] += [x["calls"][name] for x in rs]
        summary["categories"][cat] = c

    ov = summary["overall"]
    if any(obj.values()):
        ov["objective_pass_rate"] = {name: round(sum(obj[name]) / len(obj[name]), 3) for name in contestants}
        ov["objective_n"] = len(next(iter(obj.values())))
    if jwins.values() and (sum(jwins.values()) + jties):
        ov["judge_wins"] = jwins
        ov["judge_ties"] = jties
    ov["avg_latency_s"] = {name: round(sum(lat[name]) / len(lat[name]), 1) for name in contestants}
    ov["avg_calls"] = {name: round(sum(calls[name]) / len(calls[name]), 1) for name in contestants}
    return summary


def to_markdown(summary, meta):
    cs = meta["contestants"]
    L = [
        "# Frontier model vs open-weight aggregation — benchmark",
        "",
        f"- **Contestants:** {', '.join(f'`{c}`' for c in cs)}",
        f"- **opus:** `{meta['opus']}` (1 call) · **panel (fusion/debate):** {', '.join(f'`{m}`' for m in meta['panel'])}",
        f"- **fusion** = parallel answers + 1 aggregator (0 debate rounds) · **debate** = full debate to majority + synthesize",
        f"- **Judge:** `{meta['judge']}`  |  **Repeats:** {meta['repeats']}",
        "",
        "## Per-category (objective pass rate)",
        "",
        "| Category | n | " + " | ".join(cs) + " |",
        "|---|--:|" + "|".join("--:" for _ in cs) + "|",
    ]
    for cat, c in summary["categories"].items():
        if "objective_pass_rate" in c:
            cells = " | ".join(f"{c['objective_pass_rate'][n]*100:.0f}%" for n in cs)
            L.append(f"| {cat} | {c['n']} | {cells} |")
    # judged categories
    judged = {cat: c for cat, c in summary["categories"].items() if "judge_wins" in c}
    if judged:
        L += ["", "## Judged categories (blind judge wins)", "", "| Category | " + " | ".join(cs) + " | tie |", "|---|" + "|".join(":-:" for _ in cs) + "|:-:|"]
        for cat, c in judged.items():
            cells = " | ".join(str(c["judge_wins"][n]) for n in cs)
            L.append(f"| {cat} | {cells} | {c['judge_ties']} |")

    ov = summary["overall"]
    L += ["", "## Overall", ""]
    if "objective_pass_rate" in ov:
        parts = " · ".join(f"**{n}** {ov['objective_pass_rate'][n]*100:.0f}%" for n in cs)
        L.append(f"- **Objective pass rate** ({ov['objective_n']} graded runs/contestant): {parts}")
    if "judge_wins" in ov:
        parts = " · ".join(f"{n} {ov['judge_wins'][n]}" for n in cs)
        L.append(f"- **Blind judge wins:** {parts} · tie {ov['judge_ties']}")
    lat = " · ".join(f"{n} ~{ov['avg_latency_s'][n]}s" for n in cs)
    cal = " · ".join(f"{n} ~{ov['avg_calls'][n]}" for n in cs)
    L.append(f"- **Avg latency:** {lat}")
    L.append(f"- **Avg model calls:** {cal}")
    return "\n".join(L)


def main(argv=None):
    global OPUS, JUDGE
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tests", default="all", help="comma-separated test ids, or 'all'.")
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--contestants", default="opus,fusion,debate", help="subset of: opus,fusion,debate")
    p.add_argument("--panel", default=",".join(PANEL), help="panel slugs for fusion/debate.")
    p.add_argument("--opus", default=OPUS)
    p.add_argument("--judge", default=JUDGE)
    p.add_argument("--out", default=os.path.join(HERE, "results", "comparison"))
    args = p.parse_args(argv)

    OPUS = args.opus
    JUDGE = args.judge
    panel = [s.strip() for s in args.panel.split(",") if s.strip()]
    contestants = [c.strip() for c in args.contestants.split(",") if c.strip() in CONTESTANTS]
    if not contestants:
        raise SystemExit("no valid contestants (choose from opus,fusion,debate)")

    spec = json.load(open(os.path.join(HERE, "tests.json")))
    all_tests = spec["tests"]
    if args.tests != "all":
        want = {x.strip() for x in args.tests.split(",")}
        all_tests = [t for t in all_tests if t["id"] in want]
    if not all_tests:
        raise SystemExit("no matching tests")

    log = lambda m: print(m, file=sys.stderr, flush=True)
    log(f"Benchmark: {len(all_tests)} test(s) x {args.repeats} | contestants={contestants} | panel={panel}")

    rows = run(all_tests, args.repeats, contestants, panel, log)
    summary = aggregate(rows, contestants)
    meta = {
        "opus": OPUS, "panel": panel, "judge": JUDGE,
        "repeats": args.repeats, "contestants": contestants,
    }

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "rows.json"), "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    with open(os.path.join(args.out, "scorecard.json"), "w") as f:
        json.dump({"meta": meta, "summary": summary}, f, indent=2, ensure_ascii=False)
    md = to_markdown(summary, meta)
    with open(os.path.join(args.out, "scorecard.md"), "w") as f:
        f.write(md)

    print("\n" + md)
    log(f"\nWrote {args.out}/scorecard.md, scorecard.json, rows.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
