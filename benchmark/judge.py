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


def multi_judge(prompt, answers, rubric, judge_model, rotate=0):
    """Blind judge among 2+ contestants. `answers` is {name: text}.

    Presentation order is rotated by `rotate` (use the repeat index) so no contestant
    sits in a fixed slot across repeats — neutralizes position bias. The judge picks
    the single best response by letter; we map it back to the contestant name.
    """
    names = list(answers.keys())
    if len(names) < 2:
        return (names[0] if names else "tie"), "fewer than 2 contestants"
    k = rotate % len(names)
    order = names[k:] + names[:k]
    letters = [chr(65 + i) for i in range(len(order))]  # A, B, C, ...

    blocks = "\n\n".join(
        f"--- Response {lab} ---\n{answers[nm]}" for lab, nm in zip(letters, order)
    )
    sys_msg = (
        "You are an impartial judge comparing several answers to the same question. "
        "Judge only on the rubric. Ignore length and style unless the rubric asks for "
        "them. Do not favor any position; you do not know which system produced which."
    )
    user = f"""Question:
{prompt}

Judging rubric: {rubric}

{blocks}

Which single response is best on the rubric? Reply with EXACTLY one letter on its own line ({", ".join(letters)}), or TIE if they are equivalent."""

    try:
        out = openrouter.chat(
            judge_model,
            [{"role": "system", "content": sys_msg}, {"role": "user", "content": user}],
            temperature=0,
            max_tokens=2000,
        )
    except Exception as e:  # noqa: BLE001
        return "tie", f"judge error: {e}"

    # Scan for standalone tokens and take the LAST one that is a valid label or TIE.
    # Taking the last avoids matching stray capitals in the judge's prose (e.g. the
    # pronoun "I", or "A" in "A response"); the actual verdict comes at the end.
    valid = set(letters)
    tokens = re.findall(r"\b([A-Z]+)\b", (out or "").upper())
    pick = next((t for t in reversed(tokens) if t in valid or t == "TIE"), None)
    if pick is None or pick == "TIE":
        return "tie", (out or "").strip()[-120:]
    winner = order[letters.index(pick)]
    return winner, f"judge picked {pick} -> {winner}"
