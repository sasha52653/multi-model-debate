"""Objective graders for the Opus-vs-consensus benchmark.

Each grader takes the model's answer text plus the test's grader config and returns
(passed: bool, detail: str). Keep them strict but tolerant of formatting noise — we
care whether the *answer* is right, not whether the model wrapped it in prose.
"""

import re


def _norm(s):
    return (s or "").strip().lower()


def _last_number(text):
    """Pull the last numeric token from a response (handles '3', '3.0', '1,234')."""
    nums = re.findall(r"-?\d[\d,]*\.?\d*", text or "")
    if not nums:
        return None
    return float(nums[-1].replace(",", ""))


def _extract_code(text):
    """Return the body of the first python code block, or the whole text if none."""
    m = re.search(r"```(?:python)?\s*(.*?)```", text or "", re.DOTALL)
    return m.group(1) if m else (text or "")


# ---- named constraint checkers (referenced by tests.json via {"type":"checker"}) ----

def _check_five_distinct_vowel_fruits(answer, cfg):
    lines = [re.sub(r"^[\s\-\*\d\.\)]+", "", ln).strip() for ln in (answer or "").splitlines()]
    items = [ln for ln in lines if ln]
    initials = [it[0].lower() for it in items if it]
    vowels = [c for c in initials if c in "aeiou"]
    distinct = set(vowels)
    ok = len(items) == 5 and len(distinct) == 5
    return ok, f"{len(items)} items, distinct starting vowels={sorted(distinct)}"


CHECKERS = {
    "five_distinct_vowel_fruits": _check_five_distinct_vowel_fruits,
}


# ---- code grader: extract a function, run it against cases ----

def _grade_code(answer, cfg):
    src = _extract_code(answer)
    ns = {}
    try:
        exec(src, ns)
    except Exception as e:  # noqa: BLE001
        return False, f"code did not exec: {type(e).__name__}: {e}"
    fn = ns.get(cfg["func"])
    if not callable(fn):
        return False, f"function {cfg['func']!r} not defined"
    passed = 0
    fails = []
    for case in cfg["cases"]:
        inp, expected = case[0], case[1]
        args = inp if isinstance(inp, list) else [inp]
        try:
            got = fn(*args)
        except Exception as e:  # noqa: BLE001 - a raise on valid input is a failure
            got = f"RAISED {type(e).__name__}"
        if got == expected:
            passed += 1
        else:
            fails.append(f"{inp!r}->{got!r}(exp {expected!r})")
    ok = passed == len(cfg["cases"])
    detail = f"{passed}/{len(cfg['cases'])} cases" + ("" if ok else "; e.g. " + "; ".join(fails[:3]))
    return ok, detail


# ---- dispatch ----

def grade(answer, cfg):
    t = cfg["type"]

    if t == "numeric":
        got = _last_number(answer)
        if got is None:
            return False, "no number found"
        exp = float(cfg["expected"])
        tol = float(cfg.get("tol", 0))
        ok = abs(got - exp) <= tol
        return ok, f"got {got}, expected {exp} (tol {tol})"

    if t == "contains_all":
        a = _norm(answer)
        missing = [p for p in cfg["patterns"] if p.lower() not in a]
        return (not missing), ("all present" if not missing else f"missing {missing}")

    if t == "contains_any":
        a = _norm(answer)
        hit = [p for p in cfg["patterns"] if p.lower() in a]
        return (bool(hit)), (f"matched {hit}" if hit else "none of the patterns present")

    if t == "rejects_premise":
        a = _norm(answer)
        neg = cfg.get("patterns", [
            "not visible", "cannot", "can't", "is not", "isn't", "myth",
            "misconception", "not true", "no human-made", "not actually",
            "false", "not the only", "incorrect", "not accurate",
        ])
        hit = [p for p in neg if p in a]
        return (bool(hit)), (f"rejected via {hit[:2]}" if hit else "appears to accept the false premise")

    if t == "checker":
        return CHECKERS[cfg["name"]](answer, cfg)

    if t == "code":
        return _grade_code(answer, cfg)

    raise ValueError(f"unknown grader type: {t}")
