"""Model panel presets for multi-model debate.

Slugs are OpenRouter model ids (verified against https://openrouter.ai/api/v1/models).
Override any of these with --models on the CLI or the `models=` argument in code.
The point of the default panel is *lineage diversity* — different base models
disagree in genuinely different ways, which is what makes a debate informative
rather than an echo chamber.
"""

# Strong, diverse open-weight panel: four different model families.
DEFAULT_PANEL = [
    "meta-llama/llama-3.3-70b-instruct",   # Meta
    "qwen/qwen3-235b-a22b-2507",           # Alibaba (Qwen)
    "deepseek/deepseek-v3.2",              # DeepSeek
    "mistralai/mistral-large-2512",        # Mistral
]

# Cheaper / faster panel for high-volume or budget-constrained debate.
CHEAP_PANEL = [
    "meta-llama/llama-3.1-8b-instruct",
    "qwen/qwen-2.5-7b-instruct",
    "google/gemma-3-12b-it",
    "mistralai/ministral-8b-2512",
]

# Reasoning-heavy panel — slower and pricier, for hard analytical questions.
REASONING_PANEL = [
    "deepseek/deepseek-r1-0528",
    "qwen/qwen3-235b-a22b-thinking-2507",
    "meta-llama/llama-3.3-70b-instruct",
    "mistralai/mistral-large-2512",
]

PRESETS = {
    "default": DEFAULT_PANEL,
    "cheap": CHEAP_PANEL,
    "reasoning": REASONING_PANEL,
}


def resolve_panel(spec):
    """Turn a panel spec into a list of model slugs.

    `spec` may be a preset name ("default"/"cheap"/"reasoning"), a comma-separated
    string of slugs, or an already-built list. Unknown preset names are treated as
    a single literal slug so callers are never silently surprised.
    """
    if spec is None:
        return list(DEFAULT_PANEL)
    if isinstance(spec, (list, tuple)):
        return list(spec)
    if spec in PRESETS:
        return list(PRESETS[spec])
    return [s.strip() for s in spec.split(",") if s.strip()]
