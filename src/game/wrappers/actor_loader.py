"""Load the configured actor backend without any LLM wrapping.

Used by the get_actor_action MCP tool to return Q-table recommendations to the
orchestrator, keeping all LLM calls in the client per PRD §6.
"""

from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from actor.base_actor import BaseActor


def load_actor_backend(role: str) -> BaseActor:
    """Return the actor backend configured via ACTOR_CLASS/ACTOR_TABLE env vars.

    Falls back to RandomActorBackend when ACTOR_CLASS is not set.
    Never calls an LLM — NL message generation belongs in the orchestrator.

    Args:
        role: "cop" or "thief".

    Returns:
        A BaseActor instance ready to call .get_action(obs).
    """
    from actor.random_actor import RandomActorBackend

    actor_class_path = os.environ.get("ACTOR_CLASS")
    if not actor_class_path:
        return RandomActorBackend()
    module_path, class_name = actor_class_path.rsplit(".", 1)
    actor_cls = getattr(importlib.import_module(module_path), class_name)
    table_path = os.environ.get("ACTOR_TABLE")
    if table_path and hasattr(actor_cls, "load"):
        return actor_cls.load(role=role, path=table_path)
    try:
        return actor_cls(role=role)
    except TypeError:
        return actor_cls()
