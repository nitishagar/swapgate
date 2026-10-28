"""LLM-synthesised rubrics (live-behind-flag; hermetic default is heuristic).

The LLM proposes check dicts as a JSON list; every check is validated against
the deterministic 7-type vocabulary and invalid ones are dropped. The heuristic
`min_length:1` base is always kept, so synthesis can never yield a vacuous
rubric. Live synthesis goes through `ProviderCompleter`, which bridges the
async provider to the sync completer protocol.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

RUBRIC_PROMPT_TEMPLATE = """Propose eval checks for outputs answering prompts like:

EXEMPLAR:
{exemplar}

TEMPLATE:
{template}

Reply with a JSON list of check objects only. Allowed check types:
- {{"type": "contains", "values": ["word1", "word2"]}}
- {{"type": "not_contains", "values": ["word"]}}
- {{"type": "regex", "pattern": "..."}}
- {{"type": "min_length", "value": 10}}
- {{"type": "max_length", "value": 500}}
- {{"type": "exact", "value": "..."}}
- {{"type": "json_keys", "keys": ["k"]}}

JSON list:"""

BASE_CHECK = {"type": "min_length", "value": 1}


class Completer(Protocol):
    def complete(self, prompt: str) -> str:
        ...


def complete_sync(provider: Any, messages: list[dict[str, str]]) -> str:
    """Bridge one async provider call into sync rubric synthesis."""
    return asyncio.run(provider.complete(messages))


class ProviderCompleter:
    """Sync completer over an async provider (live rubric synthesis)."""

    def __init__(self, provider: Any):
        self.provider = provider

    def complete(self, prompt: str) -> str:
        return complete_sync(self.provider, [{"role": "user", "content": prompt}])


def render_rubric_prompt(template: str, exemplar: str) -> str:
    return RUBRIC_PROMPT_TEMPLATE.format(template=template, exemplar=exemplar)


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def is_valid_check(check: Any) -> bool:
    """Validate one proposed check against the deterministic vocabulary."""
    if not isinstance(check, dict):
        return False
    kind = check.get("type")
    if kind == "exact":
        return isinstance(check.get("value"), str)
    if kind in ("contains", "not_contains"):
        return isinstance(check.get("value"), str) or _is_str_list(check.get("values"))
    if kind == "regex":
        return isinstance(check.get("pattern"), str)
    if kind in ("min_length", "max_length"):
        value = check.get("value")
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "json_keys":
        return _is_str_list(check.get("keys"))
    return False


def _extract_list(raw: str) -> list[Any]:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        start, end = raw.find("["), raw.rfind("]")
        if start == -1 or end <= start:
            return []
        try:
            parsed = json.loads(raw[start:end + 1])
        except (json.JSONDecodeError, ValueError):
            return []
    return parsed if isinstance(parsed, list) else []


def synthesize_rubric_llm(cluster: Any, completer: Completer) -> list[dict[str, Any]]:
    """LLM-proposed rubric with invalid checks dropped; heuristic base kept."""
    prompt = render_rubric_prompt(cluster.template, cluster.exemplar)
    proposed = _extract_list(completer.complete(prompt))
    rubric = [dict(BASE_CHECK)]
    rubric.extend(c for c in proposed if is_valid_check(c))
    return rubric
