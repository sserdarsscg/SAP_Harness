"""
Skill registry – central lookup from intent name to skill callable.

Each skill must expose a function with the signature:
    execute(params: dict) -> dict
"""

from __future__ import annotations
from typing import Callable

# Registry: intent_name -> skill execute function
_REGISTRY: dict[str, Callable[[dict], dict]] = {}


def register_skill(intent_name: str, execute_fn: Callable[[dict], dict]) -> None:
    """Register a skill function under the given intent name."""
    _REGISTRY[intent_name] = execute_fn


def get_skill(intent_name: str) -> Callable[[dict], dict] | None:
    """Look up a registered skill by intent name."""
    return _REGISTRY.get(intent_name)


def list_skills() -> list[str]:
    """Return all registered intent names."""
    return list(_REGISTRY.keys())
