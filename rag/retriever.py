"""Retriever factory: the deployed variant is chosen in agent/config.yaml (rag.variant), not in code."""
from __future__ import annotations

from functools import lru_cache

from rag.variants.base import Pipeline, invalidate, load_variant  # noqa: F401


@lru_cache(16)
def get_retriever(name: str | None = None) -> Pipeline:
    if name is None:
        from agent.config import CONFIG
        name = CONFIG["rag"]["variant"]
    return load_variant(name)
