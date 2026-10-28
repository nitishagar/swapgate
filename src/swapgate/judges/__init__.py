"""Pluggable judges: deterministic, LLM-as-judge, typed-decision."""

import json

from .base import Judge, Verdict
from .deterministic import DeterministicJudge
from .llm import FixtureCompleter, LLMJudge
from .typed import LocalHeuristicBackend, TypedJudge

__all__ = [
    "Judge",
    "Verdict",
    "DeterministicJudge",
    "LLMJudge",
    "FixtureCompleter",
    "TypedJudge",
    "LocalHeuristicBackend",
    "get_judge",
]


def get_judge(name: str, fixtures_path: str = "") -> Judge:
    """Shared judge factory (CLI, scheduler). Raises ValueError."""
    if name == "deterministic":
        return DeterministicJudge()
    if name == "typed":
        return TypedJudge()
    if name == "llm":
        if not fixtures_path:
            raise ValueError("--judge llm needs --judge-fixtures (offline) or a live completer")
        with open(fixtures_path, encoding="utf-8") as fh:
            return LLMJudge(FixtureCompleter(json.load(fh)))
    raise ValueError(f"unknown judge: {name}")
