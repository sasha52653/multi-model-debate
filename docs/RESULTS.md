# Opus 4.8 vs open-weight consensus — findings

This documents a head-to-head comparison between a single frontier model
(**Anthropic Claude Opus 4.8**) and a **consensus of open-weight models** debating
on OpenRouter. It combines a structured benchmark (objective + blind-judged tests)
with a set of qualitative probes that exposed *when* consensus helps and when it
doesn't.

**TL;DR:** A diverse open-weight panel reaches near-parity with Opus on objective
tasks (**89% vs 100%** pass rate) and can even win open-ended judged questions — but
it has one hard limitation: **consensus cancels errors the models make
*independently*, and is blind to errors they *share*.** Optimize the panel for
lineage diversity, and never read unanimous agreement as "verified correct."

---

## Setup

- **Frontier contestant:** `anthropic/claude-opus-4.8` (1 call/question, via OpenRouter for a fair comparison).
- **Consensus panel:** `qwen/qwen3-235b-a22b-2507`, `deepseek/deepseek-r1-0528`, `moonshotai/kimi-k2.5`, `z-ai/glm-5` — four different labs, debating with `--synthesize`, `majority` rule, up to 3 rounds.
- **Judge (subjective tests):** `google/gemini-2.5-pro` — a neutral third lineage, shown the two answers blind with positions swapped across repeats.
- **Grading:** objective tests graded by code (numeric / exact / constraint / executed-code); subjective tests by the blind judge.

Reproduce with [`benchmark/run_benchmark.py`](../benchmark/run_benchmark.py).

---

## Benchmark scorecard (10 tests, 1 repeat — "quick pass")

| Category | Test | Opus | Consensus |
|---|---|:--:|:--:|
| counting-gotcha | r's in "strawberry" | ✅ | ✅ |
| false-premise | Great Wall from the Moon | ✅ | ✅ |
| arithmetic | multi-step apples | ✅ | ✅ |
| factual-recall | "Attention is All You Need" author | ✅ | ✅ |
| factual-recall | ARPANET first message year | ✅ | ✅ |
| code-correctness | `roman_to_int` | ✅ | ✅ |
| **code blind-spot** | `is_valid_ipv4` (Unicode edge cases) | ✅ | **❌ (7/10 cases)** |
| constraint-following | five distinct-vowel fruits | ✅ | ✅ |
| long-context | offsite city w/ distractors | ✅ | ✅ |
| **domain-reasoning** | Polymarket latency-arb (blind-judged) | — | **🏆 judge preferred consensus** |

**Overall:** Opus objective pass rate **100% (9/9)**; consensus **89% (8/9)**. Blind
judge on the one subjective question: **consensus 1 – Opus 0**.

**Cost / latency:** Opus ≈ **5s & 1 call** per question; consensus ≈ **252s & ~10
calls** per question (≈10× the calls, and far higher wall-clock because the panel
uses slow reasoning models). *This is the real trade-off, not quality.*

> Caveat: the quick pass is **n=1 per test**. Objective results are sharp (the
> pass/fail boundary is unambiguous), but the judged trading win needs repeats to
> trust. Run the full 3-repeat battery for pass *rates*.

---

## The central finding: correlated vs uncorrelated errors

The benchmark and a series of qualitative probes converge on one rule that predicts
every result we saw:

> **Consensus cancels errors models make independently. It cannot fix errors they
> all share.** Whether consensus helps is a property of *panel diversity*, not of
> reasoning horsepower.

### Where consensus matched or beat Opus (uncorrelated errors)
- **Base-rate / Bayes problem** (disease test ≈ 0.98%): all models got it
  independently; consensus = Opus.
- **Fermi estimate** (NYC coffee-shop revenue): round-0 answers spanned a 3× range
  ($1.6B–$4.8B), then the debate visibly converged to a tight ~$2.1–2.2B cluster.
  Consensus' *shown work* was tighter than a single pass.
- **Open-ended trading reasoning:** both identified "buy UP, latency arbitrage," but
  Opus hedged ("possibly yes… far from automatic") while the consensus led with a
  decisive, mechanism-named recommendation — and the neutral judge preferred it.

### Where Opus won (correlated blind spots)
- **`is_valid_ipv4` — the signature finding.** Every panel we tried — including a
  coding-specialized model and four diverse frontier reasoners — independently
  reached for Python's `str.isdigit()`. That idiom is a trap: it returns `True` for
  non-ASCII digits, so the validator **crashes** on `'1.2.3.²'` and **wrongly
  accepts** fullwidth/Arabic digits. The models *agreed unanimously* on subtly buggy
  code, and **two rounds of debate did not catch it** — because none of them saw the
  problem. Opus used an explicit ASCII check and passed all cases.

### The probe that proved the mechanism: the car-wash trap
*"I want to wash my car. The car wash is 100 ft away. Should I walk or drive?"* (You
must drive — the car has to *be* at the car wash.)

| Panel | Caught the trap at round 0 | Consensus outcome |
|---|---|---|
| DeepSeek-V3.2 + Qwen3 + Mistral | **0 of 3** | ❌ unanimously recommended *walking* |
| Qwen3 + DeepSeek-R1 + Kimi-2.5 + GLM-5 | **3 of 4** | ✅ corrected to *drive* (the lone holdout — R1 — was flipped by the debate) |

Same question, opposite outcomes — decided entirely by **whether the blind spot was
universal in the panel.** Notably, the dedicated reasoning model (R1) was the one
that fell for it; diversity, not reasoning depth, is what saved the run.

---

## Practical takeaways

1. **For correctness, diversify the panel by lineage.** Four models from four labs
   beat three strong-but-similar ones, because the failure mode you most need to
   defend against is the *shared* blind spot — and only diversity breaks it.
2. **Unanimous ≠ correct.** Read consensus as "no panelist objected." Surface
   dissent; treat agreement on anything subtle with healthy skepticism.
3. **Use the right consensus rule.** `all` for verifiable questions; `majority`/`2/3`
   for subjective ones (a strict `all` can report `no_consensus` even when the panel
   substantively agrees).
4. **Mind the cost curve.** ~10× the API calls and large wall-clock from reasoning
   models. Great for *offline* analysis at open-weight pricing; the latency is
   disqualifying for latency-sensitive live use (e.g. 5-minute binary trading).
5. **Best of both:** put a frontier model *on* the panel as one voice — it can break
   the open-weight ecosystem's correlated blind spots while the others add diversity.

---

*Generated from the session that built this project. Re-run the benchmark to refresh
the numbers; the qualitative findings are reproducible with the prompts named above.*
