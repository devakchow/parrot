#!/usr/bin/env python3
"""parrot oracle: optional second opinion from a different model family.

Reads a distilled question on stdin (never the whole repo), asks the first
available cross-vendor CLI (codex, gemini), and prints a capped answer.
Advisory only — the oracle never gates anything. Off by default
(oracle_enabled userConfig); degrades gracefully when no CLI is installed.
"""
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parrot_common import plugin_option  # noqa: E402

BACKENDS = (
    ("codex", lambda prompt: ["codex", "exec", prompt]),
    ("gemini", lambda prompt: ["gemini", "-p", prompt]),
)
MAX_PROMPT = 8_000
MAX_ANSWER = 6_000
TIMEOUT_SECONDS = 120


def main() -> int:
    if not plugin_option("oracle_enabled", False):
        print("ORACLE: disabled (enable via the oracle_enabled plugin setting)")
        return 0
    prompt = sys.stdin.read().strip()[:MAX_PROMPT]
    if not prompt:
        print("ORACLE: empty question")
        return 0
    for name, build in BACKENDS:
        if not shutil.which(name):
            continue
        try:
            result = subprocess.run(
                build(prompt), capture_output=True, text=True,
                timeout=TIMEOUT_SECONDS,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"ORACLE: {name} failed ({exc.__class__.__name__}); advisory skipped")
            return 0
        if result.returncode != 0:
            print(f"ORACLE: {name} exited {result.returncode}; advisory skipped")
            return 0
        answer = result.stdout.strip()[:MAX_ANSWER]
        print(f"ORACLE ({name}):\n{answer}")
        return 0
    print("ORACLE: unavailable (no codex or gemini CLI on PATH)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
