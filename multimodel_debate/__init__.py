"""multimodel_debate — query a panel of open-weight LLMs on OpenRouter and run
debate rounds until they reach consensus.

Public API:
    run_debate(prompt, models=..., max_rounds=..., consensus=...) -> dict
    parse_consensus(spec) -> callable
    list_models(query=..., free_only=...) -> list[dict]
    resolve_panel(spec) -> list[str]
"""

from .debate import run_debate, parse_consensus, describe_consensus
from .openrouter import chat, list_models, OpenRouterError
from .models import resolve_panel, DEFAULT_PANEL, CHEAP_PANEL, REASONING_PANEL, PRESETS

__version__ = "0.1.0"
__all__ = [
    "run_debate",
    "parse_consensus",
    "describe_consensus",
    "chat",
    "list_models",
    "OpenRouterError",
    "resolve_panel",
    "DEFAULT_PANEL",
    "CHEAP_PANEL",
    "REASONING_PANEL",
    "PRESETS",
]
