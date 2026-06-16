#!/usr/bin/env python3
"""Multi-model debate to consensus over OpenRouter.

Pipeline
--------
1. Round 0 (independent): every model answers the prompt on its own, blind to
   the others. Diversity here is the whole point — we want genuinely different
   starting positions.
2. Debate rounds (1..N): each model is shown the *other* models' current answers
   (anonymized as "Peer A/B/C" so it judges content, not reputation), asked to
   critique them, revise its own answer, and declare a verdict: AGREE means "the
   answers have converged and my revised answer reflects the shared consensus";
   DISAGREE means a substantive gap remains.
3. Stop when a quorum of models declare AGREE in the same round (consensus), or
   when max_rounds is hit (no consensus — we return the best-effort result).

The consensus reply is, by default, the converged answer of the panel's lead
model (panel order). Because the panel self-reported agreement, the final
answers are substantively equivalent; all of them are returned in `final_answers`
so you can inspect or post-process. Pass --synthesize to additionally merge the
agreed answers into one canonical reply using a panel model.

CLI
---
    export OPENROUTER_API_KEY=sk-or-...
    python debate.py "Is P=NP likely to be resolved this decade? Give your best estimate."
    python debate.py --prompt-file q.txt --panel reasoning --max-rounds 4 --json out.json
    echo "your prompt" | python debate.py -

Importable
----------
    from debate import run_debate
    result = run_debate("your prompt", models=["a","b"], max_rounds=3)
    print(result["consensus_reply"])

`run_debate` returns a JSON-serializable dict — see references/integration.md for
the full schema.
"""

import argparse
import json
import math
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

try:  # allow running both as a module and as a loose script
    from . import openrouter
    from .models import resolve_panel
except ImportError:  # pragma: no cover - script execution path
    import openrouter
    from models import resolve_panel


# Verdict: tolerate markdown decoration and optional colon between the keyword and
# the vote, e.g. "VERDICT: AGREE", "**VERDICT:** AGREE", "### Verdict — DISAGREE".
VERDICT_RE = re.compile(r"VERDICT\b[\s:*_\-—–>#]{0,12}(AGREE|DISAGREE)", re.IGNORECASE)


def _extract_section(text, name, stop_names):
    """Pull the body of a labeled section, tolerant of how models format headers.

    Small/instruction-light models often write headers as markdown (``**ANSWER**``,
    ``### ANSWER``, ``**ANSWER:**``) rather than the plain ``ANSWER:`` we ask for.
    We anchor the header to the start of a line, allow leading ``#``/``*``/``_``/``>``
    decoration and an optional colon, then capture everything up to the next known
    section header. Returns None if the header isn't found so the caller can fall back.
    """
    stops = "|".join(stop_names) if stop_names else r"\Z\B"  # never-match if no stops
    pat = re.compile(
        r"(?is)(?:^|\n)[ \t>]*(?:#{1,6}[ \t]*)?[*_]{0,3}[ \t]*"
        + re.escape(name)
        + r"[ \t]*[*_]{0,3}[ \t]*:?[ \t]*[*_]{0,3}[ \t]*"  # header + optional colon/markdown
        + r"(.*?)"
        + r"(?=(?:\n[ \t>]*(?:#{1,6}[ \t]*)?[*_]{0,3}[ \t]*(?:"
        + stops
        + r")\b)|\Z)"
    )
    m = pat.search(text)
    return m.group(1).strip() if m else None


def parse_consensus(spec):
    """Turn a consensus spec into a rule `f(n_live) -> required AGREE count`.

    Accepted forms (string or number):
      "all" / "unanimous" / "full"   -> every live model must agree
      "majority" / "most"            -> more than half
      an integer like 2 or "3"       -> at least that many (a count, e.g. "2 of 3")
      a fraction like "2/3" or 0.66  -> at least that share of live models

    Whatever the spec, the floor is 2 — a single model "agreeing" with itself isn't
    consensus. Counts and fractions are clamped to the number of models still live,
    so a "3 of 4" rule still resolves sensibly if one model drops out.
    """
    if callable(spec):
        return spec
    if spec is None or isinstance(spec, bool):
        spec = "all"

    if isinstance(spec, int):
        k = spec
        return lambda n, k=k: max(2, min(k, n))
    if isinstance(spec, float):
        f = spec
        if f > 1:  # a float like 3.0 means a count, not a share
            return lambda n, k=int(f): max(2, min(k, n))
        return lambda n, f=f: max(2, min(n, math.ceil(f * n)))

    s = str(spec).strip().lower()
    if s in ("all", "unanimous", "unanimity", "everyone", "full"):
        return lambda n: n
    if s in ("majority", "most"):
        return lambda n: max(2, n // 2 + 1)
    if "/" in s:
        a, b = s.split("/", 1)
        f = float(a) / float(b)
        return lambda n, f=f: max(2, min(n, math.ceil(f * n)))
    if re.fullmatch(r"\d+", s):
        return lambda n, k=int(s): max(2, min(k, n))
    try:
        f = float(s)
    except ValueError:
        raise ValueError(
            f"Unrecognized consensus spec: {spec!r}. Use 'all', 'majority', a count "
            f"like 2, or a fraction like 2/3 or 0.66."
        )
    if f > 1:
        return lambda n, k=int(f): max(2, min(k, n))
    return lambda n, f=f: max(2, min(n, math.ceil(f * n)))


def describe_consensus(spec, n):
    """Human-readable description of the rule for the panel size `n`, for prompts/logs."""
    rule = parse_consensus(spec)
    needed = rule(n)
    s = str(spec).strip().lower() if not isinstance(spec, (int, float)) else spec
    if s in ("all", "unanimous", "unanimity", "everyone", "full", None):
        return f"ALL {n} panelists must AGREE."
    if s in ("majority", "most"):
        return f"a majority ({needed} of {n}) must AGREE."
    return f"at least {needed} of {n} panelists must AGREE."


def _peer_label(i):
    """A, B, C, ... Z, AA, AB, ..."""
    label = ""
    i += 1
    while i > 0:
        i, rem = divmod(i - 1, 26)
        label = chr(65 + rem) + label
    return label


def _initial_messages(prompt, system):
    sys_msg = system or (
        "You are one expert on a panel that will debate toward a shared answer. "
        "Answer the user's question as well as you can. Be substantive and specific; "
        "state assumptions and reasoning briefly so peers can scrutinize them."
    )
    return [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": prompt},
    ]


def _debate_messages(prompt, own_answer, peer_answers, system, quorum_desc):
    """Build the critique+revise prompt for one model in a debate round.

    `peer_answers` is a list of (label, text) for the OTHER models only.
    """
    peers_block = "\n\n".join(
        f"### Peer {label}\n{text.strip()}" for label, text in peer_answers
    )
    sys_msg = system or (
        "You are one expert on a panel debating toward a shared, correct answer. "
        "Judge ideas on their merits, not their source. Concede points that are "
        "right and defend points that are wrong only with reasons. The goal is the "
        "best collective answer, not winning."
    )
    user = f"""Original question:
{prompt}

Your current answer:
{own_answer.strip()}

Other panelists' current answers (anonymized):
{peers_block}

Now do three things, in this exact format:

CRITIQUE:
<2-5 sentences: where peers are right, where they are wrong or incomplete, and why. Be specific.>

ANSWER:
<your single best revised answer to the original question, standalone and complete. Incorporate any peer points you now agree with.>

VERDICT: AGREE or DISAGREE
<AGREE only if the panel's answers have genuinely converged and your ANSWER above reflects that shared consensus. DISAGREE if a substantive difference remains. {quorum_desc} One short sentence of justification.>
"""
    return [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": user},
    ]


def _parse_response(text):
    """Extract (critique, answer, verdict) from a debate-round response.

    Robust to models that drift from the template: if a section header is missing
    we fall back to sensible defaults (whole text = answer, verdict = DISAGREE) so
    a sloppy formatter never forces a false consensus.
    """
    verdict_match = VERDICT_RE.search(text)
    verdict = verdict_match.group(1).upper() if verdict_match else "DISAGREE"

    critique = _extract_section(text, "CRITIQUE", ["ANSWER", "VERDICT"]) or ""

    answer = _extract_section(text, "ANSWER", ["VERDICT", "CRITIQUE"])
    if not answer:
        # No recognizable ANSWER header — strip any trailing VERDICT line so the
        # raw text we fall back to is at least free of the scaffolding.
        answer = VERDICT_RE.split(text)[0].strip() if verdict_match else text.strip()

    return critique, answer, verdict


def _run_parallel(jobs, max_workers):
    """jobs: dict[key] -> callable. Returns dict[key] -> result-or-exception."""
    out = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(fn): key for key, fn in jobs.items()}
        for fut in as_completed(futs):
            key = futs[fut]
            try:
                out[key] = fut.result()
            except Exception as e:  # noqa: BLE001 - we want to capture any failure per-model
                out[key] = e
    return out


def run_debate(
    prompt,
    models=None,
    max_rounds=3,
    consensus="all",
    quorum=None,
    temperature=0.7,
    max_tokens=2048,
    system=None,
    synthesize=False,
    mode="debate",
    aggregator=None,
    on_event=None,
):
    """Run a multi-model debate (or a single-pass fusion) and return a result dict.

    Parameters
    ----------
    prompt : str
    models : list[str] | str | None   panel slugs, a preset name, or None for default
    mode : "debate" | "fusion"        "debate" = independent answers, then rounds of
                                      mutual critique/revision to consensus. "fusion"
                                      = independent answers in parallel, then ONE
                                      aggregator call fuses them (no debate rounds).
                                      Fusion forces max_rounds=0 and synthesize=True.
    aggregator : str | None           model used for the synthesize/fuse step;
                                      defaults to the lead panel model.
    max_rounds : int                  max debate rounds (ignored in fusion mode)
    consensus : str | int | float     stop rule: "all" | "majority" | a count like 2
                                      | a fraction like "2/3" or 0.66 (debate mode only)
    quorum : float | None             deprecated alias for `consensus` (a fraction)
    synthesize : bool                 if True, merge the final answers into one reply
                                      via the aggregator (always on in fusion mode)
    on_event : callable(str) | None   progress callback for logging
    """
    panel = resolve_panel(models)
    if len(panel) < 2:
        raise ValueError("Need at least 2 models on the panel.")

    if mode == "fusion":
        # Fusion = parallel independent answers + one aggregator. No debate.
        max_rounds = 0
        synthesize = True
    elif mode != "debate":
        raise ValueError(f"mode must be 'debate' or 'fusion', got {mode!r}")

    spec = quorum if quorum is not None else consensus
    rule = parse_consensus(spec)

    def log(msg):
        if on_event:
            on_event(msg)

    consensus_desc = describe_consensus(spec, len(panel))

    # ---- Round 0: independent answers ----
    log(f"Round 0: {len(panel)} models answering independently...")
    base_msgs = _initial_messages(prompt, system)
    jobs = {
        m: (lambda m=m: openrouter.chat(m, base_msgs, temperature, max_tokens))
        for m in panel
    }
    r0 = _run_parallel(jobs, max_workers=len(panel))

    live = {}  # model -> current answer
    dropped = {}  # model -> error string
    for m in panel:
        res = r0[m]
        if isinstance(res, Exception):
            dropped[m] = str(res)
            log(f"  ! {m} failed and was dropped: {res}")
        elif not (res or "").strip():
            # openrouter.chat returns "" for thinking models that spent their budget
            # without emitting content — a clean miss, not a usable answer.
            dropped[m] = "empty response (no content returned)"
            log(f"  ! {m} returned an empty answer and was dropped.")
        else:
            live[m] = res

    if len(live) < 2:
        return {
            "status": "error",
            "mode": mode,
            "error": "Fewer than 2 models produced an initial answer.",
            "panel": panel,
            "dropped": dropped,
            "rounds_used": 0,
            "consensus_reply": next(iter(live.values()), None),
            "final_answers": live,
            "transcript": [{"round": 0, "answers": {m: {"answer": a} for m, a in live.items()}}],
        }

    transcript = [
        {"round": 0, "answers": {m: {"answer": live[m]} for m in live}}
    ]

    status = "no_consensus"
    rounds_used = 0
    agreement = None

    # ---- Debate rounds ----
    for rnd in range(1, max_rounds + 1):
        rounds_used = rnd
        current_models = list(live.keys())
        labels = {m: _peer_label(i) for i, m in enumerate(current_models)}
        log(f"Round {rnd}: {len(current_models)} models critiquing & revising...")

        def make_job(m):
            peers = [(labels[o], live[o]) for o in current_models if o != m]
            msgs = _debate_messages(prompt, live[m], peers, system, consensus_desc)
            return lambda: openrouter.chat(m, msgs, temperature, max_tokens)

        jobs = {m: make_job(m) for m in current_models}
        results = _run_parallel(jobs, max_workers=len(current_models))

        round_record = {"round": rnd, "answers": {}}
        verdicts = {}
        for m in current_models:
            res = results[m]
            if isinstance(res, Exception):
                dropped[m] = str(res)
                live.pop(m, None)
                log(f"  ! {m} failed mid-debate and was dropped: {res}")
                continue
            if not (res or "").strip():
                dropped[m] = "empty response mid-debate"
                live.pop(m, None)
                log(f"  ! {m} returned an empty answer mid-debate and was dropped.")
                continue
            critique, answer, verdict = _parse_response(res)
            live[m] = answer
            verdicts[m] = verdict
            round_record["answers"][m] = {
                "critique": critique,
                "answer": answer,
                "verdict": verdict,
                "label": labels[m],
            }
        transcript.append(round_record)

        if len(live) < 2:
            status = "error" if not live else "no_consensus"
            log("  Panel collapsed below 2 live models; stopping.")
            break

        needed = rule(len(live))
        agree = [m for m in live if verdicts.get(m) == "AGREE"]
        disagree = [m for m in live if verdicts.get(m) != "AGREE"]
        agreement = {"round": rnd, "agree": agree, "disagree": disagree, "needed": needed}
        log(f"  Verdicts: {len(agree)}/{len(live)} AGREE (need {needed})")

        if len(agree) >= needed:
            status = "consensus"
            log(f"  Consensus reached in round {rnd}.")
            break

    # In fusion mode there is no consensus vote; success is simply having ≥2 answers
    # to fuse. Relabel the status so callers don't misread it as a failed debate.
    if mode == "fusion":
        status = "fusion" if len(live) >= 2 else "error"

    # ---- Pick / build the final reply ----
    # Lead model = first surviving panel member in original order.
    lead = next((m for m in panel if m in live), None)
    agg_model = aggregator or lead
    consensus_reply = live.get(lead)

    if synthesize and consensus_reply is not None and len(live) >= 2:
        if mode == "fusion":
            log(f"Fusing {len(live)} independent answers via {agg_model}...")
            sys_content = (
                "You are an aggregator. Several models answered the same question "
                "independently. Produce the single best answer: keep what they agree "
                "on, adopt the strongest correct points, reconcile conflicts in favor "
                "of the better-supported view, and drop errors and redundancy. Do not "
                "merely concatenate."
            )
            user_label = "Independent answers"
        else:
            log(f"Synthesizing final canonical reply via {agg_model}...")
            sys_content = (
                "You are merging several near-identical converged answers from a "
                "panel into one clean, complete final answer. Keep everything the "
                "versions agree on, fold in any unique correct detail, drop "
                "redundancy, and do not introduce new claims the versions did not make."
            )
            user_label = "Converged versions"
        labels = {m: _peer_label(i) for i, m in enumerate(live)}
        merged_block = "\n\n".join(
            f"### Version {labels[m]}\n{live[m].strip()}" for m in live
        )
        synth_msgs = [
            {"role": "system", "content": sys_content},
            {
                "role": "user",
                "content": f"Original question:\n{prompt}\n\n{user_label}:\n{merged_block}\n\nProduce the single best final answer:",
            },
        ]
        try:
            consensus_reply = openrouter.chat(agg_model, synth_msgs, temperature, max_tokens)
        except Exception as e:  # noqa: BLE001
            log(f"  ! Aggregation failed ({e}); falling back to lead model's answer.")

    return {
        "status": status,
        "mode": mode,
        "rounds_used": rounds_used,
        "consensus_rule": str(spec),
        "panel": panel,
        "live_models": list(live.keys()),
        "dropped": dropped,
        "agreement": agreement,
        "consensus_reply": consensus_reply,
        "lead_model": lead,
        "aggregator_model": agg_model if synthesize else None,
        "final_answers": dict(live),
        "synthesized": bool(synthesize),
        "transcript": transcript,
    }


def run_fusion(prompt, models=None, aggregator=None, **kwargs):
    """Convenience wrapper: parallel independent answers + one aggregator (no debate).

    Equivalent to run_debate(..., mode="fusion"). Cheaper and faster than debate and,
    in our benchmarks, matches it on objective tasks — see docs/RESULTS.md.
    """
    return run_debate(prompt, models=models, mode="fusion", aggregator=aggregator, **kwargs)


def _print_models(query=None, free_only=False):
    """Print the OpenRouter catalogue (optionally filtered) as an aligned table."""
    rows = openrouter.list_models(query=query, free_only=free_only)
    for r in rows:
        price = (
            "free"
            if r["is_free"]
            else f"${r['prompt_price']}/${r['completion_price']} per tok"
        )
        ctx = f"{r['context']:,}" if isinstance(r["context"], int) else "?"
        print(f"{r['id']:<50}  ctx={ctx:>9}  {price}")
    print(f"\n{len(rows)} model(s)" + (f" matching {query!r}" if query else ""), file=sys.stderr)
    return rows


def _pick_models(query=None, free_only=False):
    """Interactively list models and let the user choose by number. Returns slugs."""
    rows = openrouter.list_models(query=query, free_only=free_only)
    if not rows:
        raise SystemExit("No models matched; nothing to pick from.")
    for i, r in enumerate(rows):
        tag = " (free)" if r["is_free"] else ""
        print(f"  [{i:>3}] {r['id']}{tag}", file=sys.stderr)
    raw = input("\nEnter the numbers of the models for the panel (comma-separated): ")
    chosen = []
    for tok in raw.replace(" ", "").split(","):
        if tok.isdigit() and 0 <= int(tok) < len(rows):
            chosen.append(rows[int(tok)]["id"])
    if len(chosen) < 2:
        raise SystemExit("Pick at least 2 models for a debate.")
    return chosen


def _read_prompt(args):
    if args.prompt_file:
        with open(args.prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    if args.prompt == "-" or (args.prompt is None and not sys.stdin.isatty()):
        return sys.stdin.read()
    if args.prompt:
        return args.prompt
    raise SystemExit("No prompt given. Pass a prompt, --prompt-file, or pipe via stdin with '-'.")


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Run a multi-model debate to consensus over OpenRouter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("prompt", nargs="?", help="The question/prompt (use '-' to read stdin).")
    p.add_argument("--prompt-file", help="Read the prompt from a file.")
    p.add_argument(
        "--models",
        default="default",
        help="Comma-separated OpenRouter slugs, or a preset: default | cheap | reasoning.",
    )
    p.add_argument(
        "--list-models",
        nargs="?",
        const="",
        metavar="SUBSTR",
        dest="list_models",
        help="List available OpenRouter models (optionally filtered by substring) and exit.",
    )
    p.add_argument(
        "--free-only",
        action="store_true",
        help="With --list-models / --pick, show only zero-priced (free) models.",
    )
    p.add_argument(
        "--pick",
        nargs="?",
        const="",
        metavar="SUBSTR",
        help="Interactively choose the panel from the OpenRouter list (optional filter).",
    )
    p.add_argument(
        "--mode",
        choices=["debate", "fusion"],
        default="debate",
        help="debate = rounds of mutual critique to consensus (default); "
        "fusion = parallel independent answers + one aggregator, no debate.",
    )
    p.add_argument(
        "--aggregator",
        metavar="SLUG",
        help="Model that fuses/synthesizes the final answer (default: lead panel model).",
    )
    p.add_argument("--max-rounds", type=int, default=3, help="Max debate rounds (default 3; ignored in fusion mode).")
    p.add_argument(
        "--consensus",
        default="all",
        metavar="RULE",
        help="Stop rule: all | majority | a count like 2 | a fraction like 2/3 or 0.66 "
        "(default: all = unanimous).",
    )
    p.add_argument(
        "--quorum",
        type=float,
        default=None,
        help="Deprecated alias for --consensus as a fraction (e.g. 0.75).",
    )
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--system", help="Optional custom system prompt for all models.")
    p.add_argument(
        "--synthesize",
        action="store_true",
        help="Merge the converged answers into one canonical reply (one extra call).",
    )
    p.add_argument("--json", dest="json_out", help="Write the full result dict to this JSON file.")
    p.add_argument("--quiet", action="store_true", help="Suppress progress logging on stderr.")
    p.add_argument(
        "--full",
        action="store_true",
        help="Print the full result JSON to stdout instead of just the consensus reply.",
    )
    args = p.parse_args(argv)

    # Discovery mode: print the catalogue and exit without running a debate.
    if args.list_models is not None:
        _print_models(args.list_models or None, args.free_only)
        return 0

    # Panel selection: interactive picker, or the --models spec/preset.
    if args.pick is not None:
        panel = _pick_models(args.pick or None, args.free_only)
    else:
        panel = args.models

    # Consensus: --quorum (deprecated fraction) overrides --consensus if given.
    consensus = args.quorum if args.quorum is not None else args.consensus

    prompt = _read_prompt(args)
    log = (lambda m: None) if args.quiet else (lambda m: print(m, file=sys.stderr, flush=True))

    result = run_debate(
        prompt,
        models=panel,
        max_rounds=args.max_rounds,
        consensus=consensus,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        system=args.system,
        synthesize=args.synthesize,
        mode=args.mode,
        aggregator=args.aggregator,
        on_event=log,
    )

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        log(f"Wrote full result to {args.json_out}")

    if args.full:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if not args.quiet:
            print(
                f"\n=== {result['status'].upper()} after {result['rounds_used']} round(s) "
                f"| {len(result.get('live_models', []))} model(s) ===\n",
                file=sys.stderr,
            )
        print(result.get("consensus_reply") or "(no answer produced)")

    return 0 if result["status"] in ("consensus", "no_consensus") else 1


if __name__ == "__main__":
    raise SystemExit(main())
