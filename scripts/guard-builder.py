#!/usr/bin/env python3
"""parrot builder guard: PreToolUse hook on Edit|Write.

Blocks the parrot:builder agent from modifying test files or check
configuration, so the loop cannot weaken its own verification. No-ops for
every other agent and for the main thread.
"""
import json
import sys
from fnmatch import fnmatch
from pathlib import PurePath
from typing import Optional

TEST_DIR_SEGMENTS = {"test", "tests", "__tests__", "spec", "specs"}
TEST_FILE_GLOBS = ("*.test.*", "*.spec.*", "*_test.*", "test_*.py", "conftest.py")
CHECK_CONFIG_GLOBS = (
    ".eslintrc*", "eslint.config.*", "tsconfig*.json", "jest.config.*",
    "vitest.config.*", "playwright.config.*", "cypress.config.*", "karma.conf.*",
    "biome.json*", "pytest.ini", "mypy.ini", ".flake8", "ruff.toml", ".ruff.toml",
    "setup.cfg", "pyproject.toml", ".golangci.*", ".rubocop.yml", "phpunit.xml*",
)


def guarded_kind(path_str: str) -> Optional[str]:
    path = PurePath(path_str)
    name = path.name
    if any(part.lower() in TEST_DIR_SEGMENTS for part in path.parts[:-1]):
        return "a file in a test directory"
    if any(fnmatch(name, glob) for glob in TEST_FILE_GLOBS):
        return "a test file"
    if any(fnmatch(name, glob) for glob in CHECK_CONFIG_GLOBS):
        return "check configuration"
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("agent_type") != "parrot:builder":
        return 0
    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    kind = guarded_kind(file_path)
    if kind is None:
        return 0
    print(
        f"parrot guard: builder may not modify {kind} ({file_path}). "
        "Fix the implementation instead. If the task genuinely requires changing "
        "tests or check config, stop and report that in your final message so a "
        "human can decide.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
