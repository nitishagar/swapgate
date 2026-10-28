"""Canonical trace event: the single record every ingestor produces."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TraceEvent:
    trace_id: str
    model: str
    messages: list[dict[str, str]] = field(default_factory=list)
    output: str = ""
    timestamp: str = ""
    provider: str = ""
    status: str = "success"  # success | failure
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceEvent":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def read_jsonl(path: str) -> list[dict[str, Any]]:
    rows, _ = read_jsonl_tolerant(path)
    return rows


def read_jsonl_tolerant(path: str) -> tuple[list[dict[str, Any]], int]:
    """Read JSONL, skipping corrupt lines. Returns (rows, n_skipped)."""
    rows: list[dict[str, Any]] = []
    skipped = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    return rows, skipped


def write_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def last_user_text(messages: list[dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return content if isinstance(content, str) else json.dumps(content)
    return ""
