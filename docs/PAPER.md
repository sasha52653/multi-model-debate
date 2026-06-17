# When Does Multi-Model Aggregation Help? Debate, Fusion, and Mixture-of-Agents on Open-Weight LLMs

*A preliminary empirical report.*

**Abstract.** Combining several language models — by debate, by fusing their answers,
or by iterated mutual synthesis (Mixture-of-Agents) — is widely assumed to improve
quality and reduce errors. We test three such strategies against a single frontier
model (Claude Opus 4.8) on a small battery of objective tasks and two hallucination
benchmarks (SimpleQA, TruthfulQA), using a diverse panel of four open-weight models
on OpenRouter. We find: (1) on objective tasks with a strong, lineage-diverse panel,
all aggregation methods *and* the single frontier model tie near 100% — aggregation
adds nothing measurable; (2) aggregation cancels errors models make *independently*
but is blind to errors they *share*, so it cannot fix correlated blind spots; and (3)
most strikingly, aggregation does **not** reduce hallucination and can sharply
increase it: forcing an aggregator to commit raised single-model hallucination from
13% to 80% on hard factual questions, by suppressing the abstention ("I don't know")
that protects a cautious model. Allowing the aggregator to abstain fixes this for
single-pass fusion (80%→7%) but not for debate (53%→47%) or Mixture-of-Agents
(73%→53%). We trace this to a single mechanism: **abstention requires visible
disagreement at aggregation time, and iterative methods manufacture false agreement
that destroys it.** We conclude that single-pass fusion with an abstention-permitted
aggregator is the practical sweet spot, that panel diversity matters more than per-
model strength, and that a well-calibrated frontier model remains the strongest option
for factual recall.

---

## 1. Introduction

Ensembling language models is an appealing idea: ask several models the same question,
have them argue or pool their answers, and return a consensus that no single model
would produce alone. Multi-agent **debate** (Du et al., 2023; Irving et al., 2018),
**Mixture-of-Agents** (MoA; Wang et al., 2024), and self-consistency sampling (Wang et
al., 2023) all build on this intuition, and it underpins a growing class of agent
harnesses.

But "consensus" is an agreement mechanism, not a correctness mechanism. This report
asks a practical question: *for which tasks does aggregation actually help, and when
does it hurt?* We are particularly interested in **hallucination**, where the right
behavior is often not to answer at all — a case that sits awkwardly with methods
designed to produce a single committed answer.

We implement and compare three strategies in one harness and evaluate them with code-
based and blind model-based grading. The study is deliberately small and should be
read as an experience report, not a definitive benchmark (see §5).

## 2. Methods

**Strategies.** All operate over the same panel:
- **Fusion** — each model answers independently in parallel; one *aggregator* model
  fuses the answers into one (single pass, no interaction). This is the
  Mixture-of-Agents single layer / "OpenRouter-Fusion" pattern.
- **Debate** — each model answers, then over up to three rounds sees the others'
  (anonymized) answers, critiques them, revises *its own* answer, and votes
  AGREE/DISAGREE; the run stops at a majority of AGREE, then synthesizes.
- **MoA (iterated)** — every model re-synthesizes *all* current answers each round
  (each acts as an arbiter), repeated until the answers converge (lexical similarity)
  or stop changing, up to four rounds; the medoid answer is returned.
- **single** / **opus** — one open-weight model alone, and Claude Opus 4.8 alone, as
  baselines.

**Panel.** Four open-weight models from four labs, chosen for lineage diversity:
Llama-3.3-70B (Meta), Qwen3-235B (Alibaba), DeepSeek-V3.2 (DeepSeek), Mistral-Large
(Mistral). The single-model baseline is Llama-3.3-70B. Qualitative probes (§3.2) used
other diverse 3–4 model panels including DeepSeek-R1, Kimi-K2.5, and GLM-5. The
frontier comparator is `anthropic/claude-opus-4.8`, run via the same API for fairness.

**Tasks.**
- *Objective battery* (10 items): counting gotcha, false premise, multi-step
  arithmetic, factual recall, code correctness, a code "correlated blind-spot" probe,
  constraint-following, long-context faithfulness, and one open-ended domain-reasoning
  question (blind-judged).
- *Hallucination*: 15 items each from **SimpleQA** (Wei et al., 2024 — short
  fact-seeking questions with one indisputable answer; idiosyncratic confabulation) and
  **TruthfulQA** (Lin et al., 2022 — common misconceptions; shared/correlated error).

**Grading.** Objective items are graded programmatically (numeric/exact/constraint/
executed code); the one open-ended item and all factual items are graded by a neutral
model from a third lineage (`google/gemini-2.5-pro`), blind to which system produced
each answer. Factual grading is three-way — **correct / hallucinated (incorrect) /
abstained** — because an honest "I don't know" is not a hallucination. Every contestant
was uniformly told it may answer "I don't know."

## 3. Results

### 3.1 On objective tasks, aggregation adds nothing

On the 10-item objective battery, **opus, fusion, debate, and MoA all scored 100%** on
the nine code/exact-graded items. Debate won the single open-ended judged question over
both fusion and Opus, suggesting a narrow edge for iterative critique on open-ended
reasoning. Otherwise, a strong diverse panel matches the frontier model, and the
aggregation method is irrelevant to the outcome — it only changes the cost (§3.5).

### 3.2 Aggregation cancels independent errors, not shared ones

Across objective probes one rule recurred: **aggregation removes errors models make
independently but not errors they share.** A code task asking for an IPv4 validator
elicited the *same* bug — Python's `str.isdigit()`, which accepts non-ASCII digits —
from every model in every panel we tried, including a coding-specialized model and a
panel of four diverse frontier reasoners. The models agreed unanimously on subtly buggy
code, and debate did not catch it, because no panelist saw the problem. A common-sense
trap ("the car wash is 100 ft away; should I walk or drive?" — you must drive the car)
flipped on panel composition: a three-model panel that all shared the blind spot
agreed on the wrong answer, while a four-model, more diverse panel (in which three of
four caught it) corrected the lone holdout — notably, the dedicated reasoning model was
the one that failed. **Diversity, not per-model reasoning strength, breaks correlated
errors.** A one-clause prompt cue ("must never raise on any input") was enough to make
the panel avoid the `isdigit` trap, indicating these blind spots are often an attention
gap, not a knowledge gap.

### 3.3 Aggregation does not reduce hallucination — and can amplify it

On SimpleQA (obscure facts), with each system forced to produce an answer:

| system | correct | **hallucinated** | abstained |
|---|--:|--:|--:|
| single (Llama-70B) | 0% | 13% | 87% |
| fusion | 13% | **80%** | 7% |
| debate | 27% | **53%** | 20% |
| MoA | 20% | **73%** | 7% |
| opus | 13% | **0%** | 87% |

The cautious single model abstains on 87% of facts it does not know and therefore
rarely hallucinates (13%). Every aggregation method is *worse*, and single-pass fusion
is catastrophic (80%): the aggregator is prompted to produce an answer, so it converts
the panel's honest abstentions into confident fabrications. Empirically, **hallucination
≈ 1 − abstention.** On TruthfulQA, all systems hallucinated ~0% and differed only in
correctness (single 73% → debate 100%); the classic misconceptions appear largely
saturated for this generation of models, leaving no shared error for consensus to
amplify, and aggregation modestly improved accuracy where the knowledge was present.

### 3.4 The fix, and the mechanism: abstention needs visible disagreement

If forcing commitment is the problem, permitting abstention should be the fix. We added
an `allow_abstain` option instructing the aggregator to answer "I don't know" when the
panel's answers conflict or hedge. Re-running SimpleQA:

| system | hallucinated: forced → **+abstain** |
|---|--:|
| fusion | 80% → **7%** |
| debate | 53% → **47%** |
| MoA | 73% → **53%** |

Abstention *rescued fusion completely* but barely helped debate or MoA. This isolates
the mechanism:

> **Abstention only works when the aggregator sees genuine disagreement.** Fusion shows
> the aggregator the raw, conflicting independent answers, so it correctly abstains.
> Debate and MoA *manufacture agreement before the final answer* — through rounds of
> mutual revision — so by synthesis time the inputs look concurring and the abstain
> instruction cannot fire.

In other words, the very interaction that lets iterative methods converge also
fabricates the false consensus that suppresses honest uncertainty. Opus, by contrast,
hallucinated 0% on both sets through native calibrated abstention that no aggregation
scheme matched.

### 3.5 Cost

Per question: single/opus ≈ 1 model call (~5 s); fusion ≈ 5 calls (~66 s); debate ≈ 9
calls (~121 s); MoA ≈ 14 calls (most expensive). Latency rises sharply with reasoning
models in the panel.

## 4. Discussion

**Choose the method by failure mode, not by sophistication.**
- For **factual / open-ended generation where calibration matters**, prefer
  **single-pass fusion with abstention permitted**. It preserves the disagreement
  signal that enables honest "I don't know," recovers the cautious single-model
  hallucination rate, and costs far less than debate or MoA.
- **Iterative methods (debate, MoA) are mis-calibrated for factual recall.** Their
  convergence pressure manufactures confidence; MoA, the most aggressive mixer, is
  strictly dominated in our tests (highest cost, near-worst hallucination, no objective
  advantage). Debate retains a narrow edge only on open-ended reasoning.
- **For correctness on hard problems, diversify the panel by lineage** and consider
  adding a frontier model as one voice — diversity, not depth, breaks shared blind
  spots.
- **Read agreement as "no panelist objected," not "verified correct."** Unanimity is
  weak evidence when models share training data and therefore blind spots.

These findings echo, from a practitioner's angle, results that question whether multi-
agent debate reliably beats simpler baselines, and they sharpen the Mixture-of-Agents
picture: a single fusion layer captured all the measurable benefit, and additional
iteration was, for calibration, actively harmful.

## 5. Limitations

This is a small study: 15 items per hallucination source and 10 objective items, each
run **once** (no repeats), so absolute rates are noisy — though the largest effects
(fusion 80% vs single 13%; fusion's 80%→7% under abstention) are far too large to be
noise. The single-model baseline (Llama-3.3-70B) is unusually abstention-prone, which
inflates the contrast on SimpleQA. Panel composition varied between the formal
benchmark and the qualitative probes. The model-based grader and blind judge introduce
their own biases, and the MoA convergence test uses lexical (not semantic) similarity,
which under-detects convergence on prose. Results may not transfer to other panels,
domains, prompt styles, or model generations. We report directions and mechanisms, not
precise numbers.

## 6. Conclusion

Multi-model aggregation is not a general quality or anti-hallucination win. On easy
objective tasks a diverse open-weight panel already matches a frontier model regardless
of how it is aggregated; on hard factual questions, naïve aggregation *increases*
hallucination by suppressing abstention, and only single-pass fusion recovers when the
aggregator is allowed to say "I don't know" — because only fusion preserves the
disagreement that abstention depends on. The practical recipe: diversify the panel,
fuse in a single pass, let the aggregator abstain, and treat agreement with suspicion.

## References

- Du, Y., Li, S., Torralba, A., Tenenbaum, J. B., & Mordatch, I. (2023). *Improving Factuality and Reasoning in Language Models through Multiagent Debate.*
- Irving, G., Christiano, P., & Amodei, D. (2018). *AI Safety via Debate.*
- Lin, S., Hilton, J., & Evans, O. (2022). *TruthfulQA: Measuring How Models Mimic Human Falsehoods.* ACL.
- Manakul, P., Liusie, A., & Gales, M. (2023). *SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection.* EMNLP.
- Wang, J., et al. (2024). *Mixture-of-Agents Enhances Large Language Model Capabilities.*
- Wang, X., et al. (2023). *Self-Consistency Improves Chain of Thought Reasoning in Language Models.* ICLR.
- Wei, J., et al. (2024). *Measuring Short-Form Factuality in Large Language Models (SimpleQA).* OpenAI.

---

*Reproducible with this repository: `benchmark/run_benchmark.py` (objective/judged) and
`benchmark/hallucination.py` (SimpleQA/TruthfulQA). Raw scorecards are under
`benchmark/results/`. See [RESULTS.md](RESULTS.md) for the full data behind each claim.*
