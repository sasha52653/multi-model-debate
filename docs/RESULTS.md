# Frontier model vs open-weight aggregation — findings

This compares three ways to answer the same question:

- **opus** — a single frontier model (`anthropic/claude-opus-4.8`), one call.
- **fusion** — the panel answers independently in parallel, then *one aggregator
  model fuses* their answers. No debate. (This is the "Mixture-of-Agents" /
  OpenRouter-Fusion pattern; in this repo it's `--max-rounds 0 --synthesize`.)
- **debate** — the full engine: independent answers, then rounds of mutual
  critique and revision until a majority consensus, then synthesize.

It combines a structured benchmark (objective + blind-judged tests) with a set of
qualitative probes that exposed *when* aggregation helps and when it doesn't.

**TL;DR:**
1. On objective tasks, **all three tie at 100%** — a diverse open-weight panel,
   whether fused or debated, matches Opus.
2. **Fusion ≈ debate in quality, at roughly half the cost and latency.** Debate's
   extra rounds bought nothing measurable on the objective set; on the one
   open-ended judged question, debate did win.
3. The hard limitation is shared by both: **aggregation cancels errors the models
   make *independently*, and is blind to errors they *share*** — though a small
   prompt cue can make the panel *see* a blind spot it would otherwise miss.

Optimize for panel diversity; pick fusion for cost, debate for hard reasoning or a
dissent signal; never read agreement as "verified correct."

---

## Setup

- **Panel (fusion & debate):** `qwen/qwen3-235b-a22b-2507`, `deepseek/deepseek-r1-0528`, `moonshotai/kimi-k2.5`, `z-ai/glm-5` — four different labs. Debate uses `majority` consensus, up to 3 rounds; both fusion and debate end with a synthesize step.
- **Frontier contestant:** `anthropic/claude-opus-4.8`, one call/question, via OpenRouter for a fair comparison.
- **Judge (subjective tests):** `google/gemini-2.5-pro` — a neutral third lineage, shown all answers blind in rotated order, picking the single best.
- **Grading:** objective tests by code (numeric / exact / constraint / executed-code); subjective tests by the blind judge.

Reproduce with [`benchmark/run_benchmark.py`](../benchmark/run_benchmark.py)
(`--contestants opus,fusion,debate`).

---

## Three-way scorecard (10 tests, 1 repeat)

| Category | opus | fusion | debate |
|---|:--:|:--:|:--:|
| counting-gotcha (r's in "strawberry") | ✅ | ✅ | ✅ |
| false-premise (Great Wall from the Moon) | ✅ | ✅ | ✅ |
| arithmetic (multi-step apples) | ✅ | ✅ | ✅ |
| factual-recall ×2 (paper author, ARPANET year) | ✅ | ✅ | ✅ |
| code-correctness (`roman_to_int`) | ✅ | ✅ | ✅ |
| code blind-spot (`is_valid_ipv4`, Unicode) | ✅ | ✅ | ✅ |
| constraint-following (distinct-vowel fruits) | ✅ | ✅ | ✅ |
| long-context (offsite city w/ distractors) | ✅ | ✅ | ✅ |
| **domain-reasoning** (Polymarket latency-arb, blind-judged) | — | — | **🏆 won** |

**Objective pass rate:** opus **100%** · fusion **100%** · debate **100%** (9 graded
runs each). **Blind judge** on the one subjective question: **debate 1**, opus 0,
fusion 0.

**Cost / latency per question:**

| | objective pass | avg latency | avg model calls |
|---|:--:|--:|--:|
| opus | 100% | ~5s | 1 |
| fusion | 100% | ~66s | 5 |
| debate | 100% | ~121s | 9 |

The headline trade-off: **fusion matched debate on every objective test for ~half
the calls and ~half the wall-clock.** Debate's only edge appeared on the open-ended
reasoning question, where the iterative critique produced an answer the blind judge
preferred over both the single fuse and Opus.

> Caveat: this is **n=1 per test**. Objective pass/fail is sharp, but the single
> judged result is one sample — suggestive, not conclusive. Re-run with
> `--repeats 3` for rates. (An earlier ad-hoc run had `is_valid_ipv4` *failing* for
> the panel; see the blind-spot note below for why this run passed it.)

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
- **Open-ended trading reasoning:** all approaches identified "buy UP, latency
  arbitrage," but the blind judge preferred **debate** over *both* Opus and fusion —
  the iterative critique produced the most decisive, mechanism-named answer. This is
  the one place debate beat fusion, suggesting its edge is specific to open-ended
  reasoning where positions get sharpened through back-and-forth.

### The correlated blind spot — and that it's prompt-dependent
- **`is_valid_ipv4` — the signature finding.** In an early, *underspecified* prompt
  ("...no other characters"), every panel we tried — including a coding-specialized
  model and four diverse frontier reasoners — independently reached for Python's
  `str.isdigit()`. That idiom is a trap: it returns `True` for non-ASCII digits, so
  the validator **crashes** on `'1.2.3.²'` and **wrongly accepts** fullwidth/Arabic
  digits. The models *agreed unanimously* on subtly buggy code, and **two rounds of
  debate did not catch it** — because none of them saw the problem. Opus, prompted
  the same way, used an explicit ASCII check and passed.
- **But the blind spot is an *attention* gap, not a knowledge gap.** In the
  three-way benchmark the prompt added one clause — *"must never raise on any
  input"* — and that cue was enough: fusion **and** debate both passed all 10
  `is_valid_ipv4` cases. The models *know* `isdigit()` is unsafe; they just don't
  apply that knowledge unless nudged. Takeaway: aggregation can't fix a blind spot
  *no panelist sees*, but a small prompt cue can make them see it — cheaper and more
  reliable than adding rounds.

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

1. **Default to fusion; reach for debate selectively.** Fusion matched debate on
   every objective test for ~half the cost and latency. Pay for debate's extra
   rounds only when the task is open-ended reasoning (where it won the judged
   question) or when you specifically want a dissent signal.
2. **For correctness, diversify the panel by lineage.** Four models from four labs
   beat three strong-but-similar ones, because the failure mode you most need to
   defend against is the *shared* blind spot — and only diversity breaks it.
3. **Prompt for the blind spot.** A one-clause cue ("must never raise", "consider
   adversarial input") flipped `is_valid_ipv4` from a unanimous failure to a clean
   pass — cheaper and more reliable than more models or more rounds.
4. **Agreement ≠ correct.** Read consensus as "no panelist objected." Surface
   dissent; treat agreement on anything subtle with healthy skepticism.
5. **Use the right consensus rule (debate mode).** `all` for verifiable questions;
   `majority`/`2/3` for subjective ones (a strict `all` can report `no_consensus`
   even when the panel substantively agrees).
6. **Mind the cost curve.** Fusion ~5 calls, debate ~9, vs 1 for a single model, plus
   large wall-clock from reasoning models. Great for *offline* analysis at open-weight
   pricing; the latency is disqualifying for latency-sensitive live use (e.g. 5-minute
   binary trading).
7. **Best of both:** put a frontier model *on* the panel as one voice — it can break
   the open-weight ecosystem's correlated blind spots while the others add diversity.

---

## Does aggregation reduce hallucinations? No — on hard facts it makes them worse

Run with [`benchmark/hallucination.py`](../benchmark/hallucination.py) over 30 real
items (15 [SimpleQA](https://openai.com/index/introducing-simpleqa/) obscure facts +
15 [TruthfulQA](https://github.com/sylinrl/TruthfulQA) misconceptions), graded
three-way by a neutral model (`google/gemini-2.5-pro`): **correct / hallucinated /
abstained**. Panel = Llama-3.3-70B, Qwen3-235B, DeepSeek-V3.2, Mistral-Large;
`single` = Llama-3.3-70B alone. Each contestant was told it may answer "I don't know".

**SimpleQA (obscure facts):**

| contestant | correct | hallucinated | abstained |
|---|--:|--:|--:|
| single | 0% | 13% | 87% |
| fusion | 13% | **80%** | 7% |
| debate | 27% | **53%** | 20% |
| opus | 13% | **0%** | 87% |

**TruthfulQA (misconceptions):** all contestants **0% hallucination**; correctness
single 73% → fusion 87% → debate 100% → opus 93%.

### Findings

1. **Aggregation amplified hallucination instead of reducing it.** Fusion took the
   single model's 13% hallucination rate to **80%**. The mechanism is in the
   abstention column: the cautious single model abstains 87% of the time on facts it
   doesn't know, but **the aggregator/synthesis step is prompted to produce an
   answer**, converting honest "I don't know" into confident fabrication. Abstention
   collapsed 87%→7%; hallucination exploded. Empirically, **hallucination ≈
   (1 − abstention)**.
2. **Why the uncorrelated-error logic fails here.** Consensus cancels *votable*
   errors, but on open-ended factual recall the correct output is *abstention*, and
   aggregation destroys it. The "cancel uncorrelated mistakes" principle assumes every
   model emits a committable answer — false when the right move is not to answer.
3. **Debate hallucinates less than fusion (53% vs 80%)** because a dissenting "I don't
   know" can survive the rounds, whereas fusion's aggregator simply commits. Debate is
   the less-harmful aggregator, still far worse than leaving the cautious model alone.
4. **Opus wins decisively: 0% hallucination on both sets** via calibrated abstention —
   a real frontier-model advantage (knowing when *not* to answer).
5. **Where aggregation helps: accuracy when the knowledge is present.** On TruthfulQA,
   debate reached 100% (vs single 73%) with zero hallucination. Consensus improves
   correctness when the panel actually knows the answer — it just can't manufacture
   missing knowledge without fabricating.

Caveats: n=15/source, single repeat, and `single` is the abstention-prone Llama-70B —
absolute numbers are noisy, but the direction (fusion 80% vs single 13%) is far too
large to be noise.

### Fix: abstention-aware aggregation (`allow_abstain`)

The diagnosis above predicted the fix: let the aggregator return "I don't know" when
the panel's answers conflict or hedge, instead of forcing commitment. This is now
implemented as `run_debate(..., allow_abstain=True)` / `--allow-abstain`. Re-running
the SimpleQA half with it on:

| contestant | hallucinated: before → **after** | abstained: before → after |
|---|--:|--:|
| single | 13% → 13% | 87% → 87% |
| **fusion** | 80% → **7%** | 7% → 87% |
| debate | 53% → **47%** | 20% → 27% |
| opus | 0% → 0% | 87% → 87% |

**Fusion: solved.** Abstention-aware fusion cut hallucination 80% → 7% (12×),
recovering the cautious single-model / Opus profile. *So multi-model reduces
hallucination only if the aggregator may abstain* — forced to commit it is
catastrophic.

**Debate: barely moved (53% → 47%) — a deeper flaw.** Even permitted to abstain,
debate keeps committing to wrong answers, because its rounds manufacture a
*confident-looking agreed answer before synthesis*. The aggregator sees concurring
inputs and commits; fusion's raw conflicting answers correctly trigger abstention.
Debate's own convergence pressure (the same herding seen elsewhere) defeats
calibration. A debate-specific remedy would have to abstain on *measured* panel
disagreement, not the aggregator's read of the (falsely) converged answers.

**Residual trade-off.** fusion+abstain is *safe* but adds little over one cautious
model on facts the panel doesn't know (7% correct). debate+abstain gets more correct
(27%, the back-and-forth surfaces knowledge some members hold) but stays poorly
calibrated (47% hallucinated). **Opus still wins outright** — 0% hallucinated via
native calibration no aggregation scheme matched.

---

*Generated from the session that built this project. Re-run the benchmark to refresh
the numbers; the qualitative findings are reproducible with the prompts named above.*
