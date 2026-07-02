#!/usr/bin/env python3
"""parrot session nudge: SessionStart hook (startup|clear).

If the project has no engineering profile configured, suggests /parrot:hire —
exactly once per project, ever. Silent in non-git directories and after the
first nudge.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parrot_common import debug_log, plugin_data_dir  # noqa: E402


def main() -> int:
    payload = json.load(sys.stdin)
    debug_log(payload, "session-nudge")
    cwd = Path(payload.get("cwd") or ".").resolve()
    if not (cwd / ".git").exists():
        return 0
    if (cwd / ".parrot" / "profile.json").exists():
        return 0
    flag = plugin_data_dir() / "nudged" / hashlib.sha256(str(cwd).encode()).hexdigest()[:16]
    if flag.exists():
        return 0
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1")
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "parrot: no engineering profile configured for this project. "
                "If the user wants parrot's builder/checker loop tuned to a "
                "company-grade discipline (Google, Meta, Palantir, Jane Street, "
                "NASA/JPL, Stripe), suggest running /parrot:hire once. "
                "Until then the loop uses the google default. Do not repeat "
                "this suggestion if declined."
            ),
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
