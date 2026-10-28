"""Dependency-diet guard: test-only extras must never leak into src/."""

import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")
SRC = os.path.join(ROOT, "src", "swapgate")

BANNED_TOP_LEVELS = ("litellm",)

_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)")


def test_no_extra_imports_in_src():
    violations = []
    for dirpath, _, filenames in os.walk(SRC):
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, ROOT)
            with open(path, encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, 1):
                    match = _IMPORT_RE.match(line)
                    if match and match.group(1) in BANNED_TOP_LEVELS:
                        violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, f"extra imports in src/: {violations}"
