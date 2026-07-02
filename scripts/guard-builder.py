#!/usr/bin/env python3
"""parrot builder guard: PreToolUse hook on Edit|Write.

Blocks the parrot:builder agent from modifying test files, harness hook
files, or check configuration, so the loop cannot weaken its own
verification. Also blocks builder writes into .parrot/ (ledger integrity).
No-ops for every other agent and for the main thread.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parrot_common import debug_log, guarded_kind  # noqa: E402


def main() -> int:
    payload = json.load(sys.stdin)
    debug_log(payload, "guard-builder")
    if payload.get("agent_type") != "parrot:builder":
        return 0
    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if ".parrot" in Path(file_path).parts:
        print(
            "parrot guard: builder may not write into .parrot/ — loop artifacts "
            "are written only by the orchestrator's state CLI.",
            file=sys.stderr,
        )
        return 2
    kind = guarded_kind(file_path)
    if kind is None:
        return 0
    print(
        f"parrot guard: builder may not modify {kind} ({file_path}). "
        "Fix the implementation instead. If the task genuinely requires changing "
        "tests or check config, stop and report INFEASIBLE in your final message "
        "so a human can decide.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
