"""Blind LLM judge for subjective benchmark questions.

The two answers are presented as "Response A" / "Response B" in a caller-controlled
order (we swap on alternating repeats), so the judge can't learn a position bias and
never knows which contestant is which. It returns the winner mapped back to
'opus' / 'consensus' / 'tie'.
"""

import re

import openrouter


def blind_judge(prompt, opus_answer, consensus_answer, rubric, judge_model, swap=False):
    # swap controls which contestant is shown as "A" to neutralize position bias.
    a, b = (consensus_answer, opus_answer) if swap else (opus_answer, consensus_answer)
    a_is = "consensus" if swap else "opus"
    b_is = "opus" if swap else "consensus"

    sys_msg = (
        "You are an impartial judge comparing two answers to the same question. "
        "Judge only on the rubric given. Ignore length and style unless the rubric "
        "asks for them. Do not favor either position."
    )
    user = f"""Question:
{prompt}

Judging rubric: {rubric}

--- Response A ---
{a}

--- Response B ---
{b}

Which response is better on the rubric? Answer with EXACTLY one token on its own line:
A   (if A is clearly better)
B   (if B is clearly better)
TIE (if they are equivalent)"""

    try:
        out = openrouter.chat(
            judge_model,
            [{"role": "system", "content": sys_msg}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=2000,
        )
    except Exception as e:  # noqa: BLE001
        return "tie", f"judge error: {e}"

    m = re.search(r"\b(A|B|TIE)\b", (out or "").upper())
    token = m.group(1) if m else "TIE"
    if token == "TIE":
        return "tie", out.strip()[:120]
    winner = a_is if token == "A" else b_is
    return winner, f"judge picked {token} ({winner})"
