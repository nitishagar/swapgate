"""MCP server manifest, generated from TOOLS (single source of truth)."""

from __future__ import annotations

import json
from typing import Any

from . import __version__
from .mcp_server import SERVER_NAME, TOOLS

DESCRIPTION = "SwapGate MCP server: run model-swap eval gates from coding agents."


def build_manifest() -> dict[str, Any]:
    return {
        "name": SERVER_NAME,
        "version": __version__,
        "description": DESCRIPTION,
        "tools": [
            {"name": name, "description": spec["description"],
             "inputSchema": spec["inputSchema"]}
            for name, spec in TOOLS.items()
        ],
    }


def render_manifest() -> str:
    return json.dumps(build_manifest(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_manifest(path: str = "mcp.json") -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_manifest())


def check_manifest(path: str = "mcp.json") -> bool:
    """True iff the checked-in manifest matches a fresh render."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read() == render_manifest()
    except FileNotFoundError:
        return False
