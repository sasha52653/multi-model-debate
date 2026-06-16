"""Minimal, dependency-free OpenRouter chat client.

Uses only the Python standard library (urllib) so the debate engine can be
vendored into any harness without a pip install. If you'd rather use the
`openai` SDK pointed at OpenRouter's base_url, that works too — this module just
keeps the footprint zero.

Auth: set OPENROUTER_API_KEY in the environment (get a key at
https://openrouter.ai/keys).
"""

import json
import os
import time
import urllib.error
import urllib.request

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"


class OpenRouterError(RuntimeError):
    """Raised when a chat completion ultimately fails after retries."""


def list_models(timeout=30, query=None, free_only=False):
    """Return the live OpenRouter model catalogue as a list of dicts.

    Each entry: {id, name, context, prompt_price, completion_price, is_free}.
    `query` (case-insensitive substring) filters by id or name; `free_only` keeps
    only zero-priced models. The models endpoint is public, but we send the API key
    if present so the call works behind stricter network policies.
    """
    headers = {}
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(MODELS_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8")).get("data", [])

    q = (query or "").lower()
    out = []
    for m in data:
        pricing = m.get("pricing") or {}
        prompt_p = pricing.get("prompt")
        completion_p = pricing.get("completion")

        def _is_zero(p):
            try:
                return float(p) == 0.0
            except (TypeError, ValueError):
                return False

        is_free = _is_zero(prompt_p) and _is_zero(completion_p)
        if free_only and not is_free:
            continue
        if q and q not in (m.get("id", "") + " " + m.get("name", "")).lower():
            continue
        out.append(
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "context": m.get("context_length"),
                "prompt_price": prompt_p,
                "completion_price": completion_p,
                "is_free": is_free,
            }
        )
    out.sort(key=lambda r: r["id"] or "")
    return out


def _api_key():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not set. Get a key at https://openrouter.ai/keys "
            "and export OPENROUTER_API_KEY=sk-or-..."
        )
    return key


def chat(
    model,
    messages,
    temperature=0.7,
    max_tokens=2048,
    timeout=120,
    retries=3,
    referer="https://github.com/multi-model-debate",
    title="multi-model-debate",
):
    """Call one model and return its assistant text.

    Retries transient failures (timeouts, 429, 5xx) with exponential backoff.
    Raises OpenRouterError on a terminal failure so the caller can drop the model
    from the panel rather than crash the whole debate.
    """
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        # Optional but recommended by OpenRouter for attribution / rankings.
        "HTTP-Referer": referer,
        "X-Title": title,
    }

    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if "error" in body and body["error"]:
                raise OpenRouterError(f"{model}: API error: {body['error']}")
            choices = body.get("choices") or []
            if not choices:
                raise OpenRouterError(f"{model}: empty choices in response: {body}")
            # Thinking models (deepseek-r1, qwen3-*-thinking, kimi-k2-thinking, ...) often
            # return content=None — the answer lands under "reasoning"/"reasoning_content",
            # or the token budget was consumed mid-reasoning. Fall back across those fields
            # and NEVER return None (a None crashes every downstream .strip()/regex, which
            # turned a whole reasoning-panel run into 36/50 ERRORs). Empty string is a clean
            # miss the caller can treat as a SKIP instead of an exception.
            msg = choices[0].get("message") or {}
            text = msg.get("content")
            if not text:
                text = msg.get("reasoning") or msg.get("reasoning_content") or ""
            return text
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            last_err = OpenRouterError(f"{model}: HTTP {e.code}: {detail}")
            # Only retry on rate-limit / server errors.
            if e.code not in (408, 409, 429, 500, 502, 503, 504):
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError) as e:
            last_err = OpenRouterError(f"{model}: {type(e).__name__}: {e}")
        # backoff before next attempt
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    raise last_err or OpenRouterError(f"{model}: unknown failure")
