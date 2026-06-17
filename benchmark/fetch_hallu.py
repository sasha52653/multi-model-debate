#!/usr/bin/env python3
"""Fetch real hallucination-benchmark items into hallu_tests.json.

Two complementary sources, chosen to span the correlated/uncorrelated axis:
  - SimpleQA (OpenAI): short fact-seeking questions with one indisputable answer.
    Confabulation here is *idiosyncratic* — different models get it wrong differently
    → the case where consensus should help.
  - TruthfulQA: "imitative falsehoods" / common misconceptions. The wrong answer is
    *shared* across models trained on the same web → the case where consensus should
    NOT help. Included as the deliberate contrast.

Sampling is a deterministic stride (no randomness) so the set is reproducible.

    python fetch_hallu.py --per-source 20
"""

import argparse
import csv
import io
import json
import os
import urllib.request

SIMPLEQA_URL = "https://openaipublic.blob.core.windows.net/simple-evals/simple_qa_test_set.csv"
TRUTHFULQA_URL = "https://raw.githubusercontent.com/sylinrl/TruthfulQA/main/TruthfulQA.csv"
HERE = os.path.dirname(os.path.abspath(__file__))


def _stride(rows, n):
    if n >= len(rows):
        return rows
    step = len(rows) // n
    return [rows[i * step] for i in range(n)]


def fetch_simpleqa(n):
    raw = urllib.request.urlopen(SIMPLEQA_URL, timeout=60).read().decode()
    rows = list(csv.DictReader(io.StringIO(raw)))
    out = []
    for i, r in enumerate(_stride(rows, n)):
        out.append({
            "source": "simpleqa",
            "id": f"sqa-{i}",
            "question": r["problem"].strip(),
            "gold": r["answer"].strip(),
            "correct": [r["answer"].strip()],
            "incorrect": [],
        })
    return out


def _split(field):
    return [s.strip() for s in (field or "").split(";") if s.strip()]


def fetch_truthfulqa(n):
    raw = urllib.request.urlopen(TRUTHFULQA_URL, timeout=60).read().decode()
    rows = list(csv.DictReader(io.StringIO(raw)))
    out = []
    for i, r in enumerate(_stride(rows, n)):
        out.append({
            "source": "truthfulqa",
            "id": f"tqa-{i}",
            "question": r["Question"].strip(),
            "gold": r["Best Answer"].strip(),
            "correct": _split(r["Correct Answers"]),
            "incorrect": _split(r["Incorrect Answers"]),
            "category": r.get("Category", "").strip(),
        })
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--per-source", type=int, default=20, help="items to pull from each dataset.")
    p.add_argument("--out", default=os.path.join(HERE, "hallu_tests.json"))
    args = p.parse_args()

    items = fetch_simpleqa(args.per_source) + fetch_truthfulqa(args.per_source)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, indent=2, ensure_ascii=False)
    n_sqa = sum(1 for it in items if it["source"] == "simpleqa")
    n_tqa = sum(1 for it in items if it["source"] == "truthfulqa")
    print(f"Wrote {len(items)} items ({n_sqa} simpleqa + {n_tqa} truthfulqa) -> {args.out}")


if __name__ == "__main__":
    main()
