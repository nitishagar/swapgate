"""P6: manifest generation tests (single source: mcp_server.TOOLS)."""

import json
import os

from swapgate import __version__
from swapgate.cli import EXIT_ERROR, EXIT_OK, main
from swapgate.manifest import build_manifest, check_manifest, render_manifest
from swapgate.mcp_server import SERVER_NAME, TOOLS

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_manifest_matches_tools():
    manifest = build_manifest()
    assert manifest["name"] == SERVER_NAME
    assert manifest["version"] == __version__
    assert [t["name"] for t in manifest["tools"]] == list(TOOLS)
    for tool in manifest["tools"]:
        assert set(tool) == {"name", "description", "inputSchema"}
        assert "handler" not in json.dumps(tool)


def test_checked_in_manifest_clean():
    assert check_manifest(os.path.join(ROOT, "mcp.json"))
    assert render_manifest().endswith("\n")


def test_check_detects_drift(tmp_path):
    stale = str(tmp_path / "mcp.json")
    with open(stale, "w", encoding="utf-8") as fh:
        fh.write('{"name": "stale"}')
    assert not check_manifest(stale)
    assert not check_manifest(str(tmp_path / "missing.json"))
    assert main(["manifest", "--check", "--out", stale]) == EXIT_ERROR
    assert main(["manifest", "--out", stale]) == EXIT_OK
    assert check_manifest(stale)
