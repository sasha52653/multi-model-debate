#!/usr/bin/env python3
"""Generic harness adapter for the multi-model debate engine.

Most agent harnesses (Hermes and others) invoke a tool either by shelling out to
a command that prints JSON, or by importing a Python callable. This script does
both: pass a prompt as an argument (or JSON on stdin) and it prints a JSON result
to stdout. Pair it with `tool.json` (an OpenAI/Anthropic-style function schema)
when registering it as a callable tool.

Install the engine first (see ../../docs/INSTALL.md):
    pip install multimodel-debate        # or: pip install -e . from the repo root

Examples:
    python run.py "Should we adopt a monorepo?" --panel reasoning --consensus majority
    echo '{"prompt":"...","panel":"default","consensus":"2/3"}' | python run.py --json-stdin
"""

import argparse
import json
import sys

try:
    from multimodel_debate import run_debate
except ImportError:
    sys.exit(
        "multimodel_debate is not importable. Install it first:\n"
        "  pip install multimodel-debate   (or: pip install -e . from the repo root)\n"
        "and ensure OPENROUTER_API_KEY is set."
    )


def main():
    p = argparse.ArgumentParser(description="Run a multi-model debate and emit JSON.")
    p.add_argument("prompt", nargs="?", help="The question (omit if using --json-stdin).")
    p.add_argument("--panel", default="default", help="preset name, comma slugs, or list.")
    p.add_argument("--mode", choices=["debate", "fusion"], default="debate",
                   help="debate (default) | fusion (parallel answers + one aggregator).")
    p.add_argument("--aggregator", default=None, help="model that fuses the final answer.")
    p.add_argument("--max-rounds", type=int, default=3)
    p.add_argument("--consensus", default="majority", help="all | majority | count | fraction")
    p.add_argument("--synthesize", action="store_true")
    p.add_argument("--json-stdin", action="store_true", help="read {prompt, panel, ...} from stdin.")
    p.add_argument("--full", action="store_true", help="emit the full result dict, not the summary.")
    args = p.parse_args()

    if args.json_stdin:
        cfg = json.load(sys.stdin)
        prompt = cfg["prompt"]
        panel = cfg.get("panel", args.panel)
        mode = cfg.get("mode", args.mode)
        aggregator = cfg.get("aggregator", args.aggregator)
        max_rounds = cfg.get("max_rounds", args.max_rounds)
        consensus = cfg.get("consensus", args.consensus)
        synthesize = cfg.get("synthesize", args.synthesize)
    else:
        if not args.prompt:
            p.error("provide a prompt or use --json-stdin")
        prompt, panel, mode, aggregator = args.prompt, args.panel, args.mode, args.aggregator
        max_rounds, consensus, synthesize = args.max_rounds, args.consensus, args.synthesize

    result = run_debate(
        prompt,
        models=panel,
        mode=mode,
        aggregator=aggregator,
        max_rounds=max_rounds,
        consensus=consensus,
        synthesize=synthesize,
    )

    if args.full:
        out = result
    else:
        out = {
            "consensus_reply": result["consensus_reply"],
            "mode": result.get("mode"),
            "reached_consensus": result["status"] == "consensus",
            "status": result["status"],
            "rounds_used": result["rounds_used"],
            "dissenters": (result.get("agreement") or {}).get("disagree", []),
            "dropped": result["dropped"],
        }
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
