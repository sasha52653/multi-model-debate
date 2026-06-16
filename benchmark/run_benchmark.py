#!/usr/bin/env python3
"""Benchmark: a single frontier model (Opus) vs an open-weight debate consensus.

For each test, both contestants answer the same prompt under the same API:
  - Opus:      one call to anthropic/claude-opus-4.8 via OpenRouter.
  - Consensus: the debate engine over a diverse open-weight panel (--synthesize on).

Objective tests are graded programmatically (exact/numeric/code/constraint). Subjective
tests go to a blind, neutral judge model that never learns which answer is which.
Each test is repeated N times (defaults to 3) because both contestants are stochastic;
we report pass *rates*, plus a cost proxy (model calls) and wall-clock latency.

Usage:
    export OPENROUTER_API_KEY=sk-or-...
    python run_benchmark.py                       # full battery, 3 repeats
    python run_benchmark.py --tests rcount,roman --repeats 1   # quick subset
    python run_benchmark.py --out results/run1    # where to write the scorecard
"""

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# Put the package dir on the path so its modules import flat (openrouter/models/debate),
# matching how debate.py's import fallback and judge.py expect them.
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


def opus_answer(prompt):
    t0 = time.time()
    ans = openrouter.chat(
        OPUS, [{"role": "user", "content": prompt}], temperature=0.7, max_tokens=MAX_TOKENS
    )
    return ans, time.time() - t0


def consensus_answer(prompt, panel, consensus_rule):
    t0 = time.time()
    res = run_debate(
        prompt,
        models=panel,
        max_rounds=3,
        consensus=consensus_rule,
        synthesize=True,
        max_tokens=MAX_TOKENS,
    )
    calls = len(panel) * (1 + res["rounds_used"]) + (1 if res["synthesized"] else 0)
    return res["consensus_reply"], res, calls, time.time() - t0


def run(tests, repeats, panel, consensus_rule, log):
    rows = []
    for t in tests:
        for r in range(repeats):
            tag = f"{t['id']} (rep {r + 1}/{repeats})"
            log(f"  running {tag} ...")
            try:
                opus, opus_lat = opus_answer(t["prompt"])
            except Exception as e:  # noqa: BLE001
                opus, opus_lat = f"(opus error: {e})", 0.0
            cons, cres, calls, cons_lat = consensus_answer(t["prompt"], panel, consensus_rule)

            row = {
                "id": t["id"],
                "category": t["category"],
                "repeat": r,
                "opus_latency_s": round(opus_lat, 1),
                "consensus_latency_s": round(cons_lat, 1),
                "consensus_calls": calls,
                "consensus_status": cres["status"],
                "consensus_rounds": cres["rounds_used"],
                "opus_answer": opus,
                "consensus_answer": cons,
            }

            g = t["grader"]
            if g["type"] == "judge":
                winner, detail = judge.blind_judge(
                    t["prompt"], opus, cons, g["rubric"], JUDGE, swap=(r % 2 == 1)
                )
                row.update(mode="judge", winner=winner, detail=detail)
                log(f"    judge -> {winner}")
            else:
                op_ok, op_d = graders.grade(opus, g)
                co_ok, co_d = graders.grade(cons, g)
                row.update(
                    mode="objective",
                    opus_pass=op_ok,
                    consensus_pass=co_ok,
                    opus_detail=op_d,
                    consensus_detail=co_d,
                )
                log(f"    opus={'PASS' if op_ok else 'FAIL'}  consensus={'PASS' if co_ok else 'FAIL'}")
            rows.append(row)
    return rows


def aggregate(rows):
    cats = {}
    for row in rows:
        cats.setdefault(row["category"], []).append(row)

    summary = {"categories": {}, "overall": {}}
    obj_opus, obj_cons = [], []
    j_opus = j_cons = j_tie = 0
    lat_opus, lat_cons, calls = [], [], []

    for cat, rs in cats.items():
        c = {"n": len(rs)}
        objs = [r for r in rs if r["mode"] == "objective"]
        jus = [r for r in rs if r["mode"] == "judge"]
        if objs:
            o = sum(r["opus_pass"] for r in objs) / len(objs)
            v = sum(r["consensus_pass"] for r in objs) / len(objs)
            c["opus_pass_rate"] = round(o, 3)
            c["consensus_pass_rate"] = round(v, 3)
            obj_opus += [r["opus_pass"] for r in objs]
            obj_cons += [r["consensus_pass"] for r in objs]
        if jus:
            c["judge_opus_wins"] = sum(r["winner"] == "opus" for r in jus)
            c["judge_consensus_wins"] = sum(r["winner"] == "consensus" for r in jus)
            c["judge_ties"] = sum(r["winner"] == "tie" for r in jus)
            j_opus += c["judge_opus_wins"]
            j_cons += c["judge_consensus_wins"]
            j_tie += c["judge_ties"]
        c["avg_opus_latency_s"] = round(sum(r["opus_latency_s"] for r in rs) / len(rs), 1)
        c["avg_consensus_latency_s"] = round(sum(r["consensus_latency_s"] for r in rs) / len(rs), 1)
        c["avg_consensus_calls"] = round(sum(r["consensus_calls"] for r in rs) / len(rs), 1)
        summary["categories"][cat] = c
        lat_opus += [r["opus_latency_s"] for r in rs]
        lat_cons += [r["consensus_latency_s"] for r in rs]
        calls += [r["consensus_calls"] for r in rs]

    ov = summary["overall"]
    if obj_opus:
        ov["objective_opus_pass_rate"] = round(sum(obj_opus) / len(obj_opus), 3)
        ov["objective_consensus_pass_rate"] = round(sum(obj_cons) / len(obj_cons), 3)
        ov["objective_n"] = len(obj_opus)
    if j_opus + j_cons + j_tie:
        ov["judge_opus_wins"] = j_opus
        ov["judge_consensus_wins"] = j_cons
        ov["judge_ties"] = j_tie
    ov["avg_opus_latency_s"] = round(sum(lat_opus) / len(lat_opus), 1)
    ov["avg_consensus_latency_s"] = round(sum(lat_cons) / len(lat_cons), 1)
    ov["avg_consensus_calls"] = round(sum(calls) / len(calls), 1)
    ov["calls_ratio"] = f"{ov['avg_consensus_calls']:.0f}x Opus (1 call)"
    return summary


def to_markdown(summary, meta):
    L = [
        "# Opus vs open-weight consensus — benchmark",
        "",
        f"- **Opus:** `{meta['opus']}` (1 call/question)",
        f"- **Consensus panel:** {', '.join(f'`{m}`' for m in meta['panel'])}",
        f"- **Judge (subjective):** `{meta['judge']}`",
        f"- **Repeats per test:** {meta['repeats']}  |  **Consensus rule:** {meta['consensus_rule']}",
        "",
        "## Per-category",
        "",
        "| Category | n | Opus pass | Consensus pass | Judge (O/C/T) | Opus lat | Cons lat | Cons calls |",
        "|---|--:|--:|--:|:--:|--:|--:|--:|",
    ]
    for cat, c in summary["categories"].items():
        op = f"{c['opus_pass_rate']*100:.0f}%" if "opus_pass_rate" in c else "—"
        co = f"{c['consensus_pass_rate']*100:.0f}%" if "consensus_pass_rate" in c else "—"
        jd = (
            f"{c.get('judge_opus_wins',0)}/{c.get('judge_consensus_wins',0)}/{c.get('judge_ties',0)}"
            if "judge_opus_wins" in c else "—"
        )
        L.append(
            f"| {cat} | {c['n']} | {op} | {co} | {jd} | "
            f"{c['avg_opus_latency_s']}s | {c['avg_consensus_latency_s']}s | {c['avg_consensus_calls']} |"
        )
    ov = summary["overall"]
    L += ["", "## Overall", ""]
    if "objective_opus_pass_rate" in ov:
        L.append(
            f"- **Objective pass rate** ({ov['objective_n']} graded runs): "
            f"Opus **{ov['objective_opus_pass_rate']*100:.0f}%** vs "
            f"Consensus **{ov['objective_consensus_pass_rate']*100:.0f}%**"
        )
    if "judge_opus_wins" in ov:
        L.append(
            f"- **Blind judge:** Opus {ov['judge_opus_wins']} / "
            f"Consensus {ov['judge_consensus_wins']} / Tie {ov['judge_ties']}"
        )
    L.append(
        f"- **Cost/latency:** Opus ~{ov['avg_opus_latency_s']}s & 1 call; "
        f"Consensus ~{ov['avg_consensus_latency_s']}s & ~{ov['avg_consensus_calls']} calls "
        f"({ov['calls_ratio']})"
    )
    return "\n".join(L)


def main(argv=None):
    global OPUS, JUDGE
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tests", default="all", help="comma-separated test ids, or 'all'.")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--panel", default=",".join(PANEL), help="comma-separated consensus panel slugs.")
    p.add_argument("--opus", default=OPUS, help="the frontier contestant model.")
    p.add_argument("--judge", default=JUDGE, help="neutral judge model for subjective tests.")
    p.add_argument("--consensus", default="majority", help="consensus rule for the panel.")
    p.add_argument("--out", default=os.path.join(HERE, "results", "latest"), help="output dir prefix.")
    args = p.parse_args(argv)

    OPUS = args.opus
    JUDGE = args.judge
    panel = [s.strip() for s in args.panel.split(",") if s.strip()]

    spec = json.load(open(os.path.join(HERE, "tests.json")))
    all_tests = spec["tests"]
    if args.tests != "all":
        want = {x.strip() for x in args.tests.split(",")}
        all_tests = [t for t in all_tests if t["id"] in want]
    if not all_tests:
        raise SystemExit("no matching tests")

    log = lambda m: print(m, file=sys.stderr, flush=True)
    log(f"Benchmark: {len(all_tests)} test(s) x {args.repeats} repeat(s) | Opus={OPUS} | panel={panel}")

    rows = run(all_tests, args.repeats, panel, args.consensus, log)
    summary = aggregate(rows)
    meta = {
        "opus": OPUS, "panel": panel, "judge": JUDGE,
        "repeats": args.repeats, "consensus_rule": args.consensus,
    }

    outdir = args.out
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "rows.json"), "w") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    with open(os.path.join(outdir, "scorecard.json"), "w") as f:
        json.dump({"meta": meta, "summary": summary}, f, indent=2, ensure_ascii=False)
    md = to_markdown(summary, meta)
    with open(os.path.join(outdir, "scorecard.md"), "w") as f:
        f.write(md)

    print("\n" + md)
    log(f"\nWrote {outdir}/scorecard.md, scorecard.json, rows.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
