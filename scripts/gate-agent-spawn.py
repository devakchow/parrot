#!/usr/bin/env python3
"""parrot spawn gate: PreToolUse hook on Task|Agent.

The deterministic max-cycles rule: counts parrot:builder spawns per session
and denies the spawn that would exceed the cap. The counter lives here, not
in the orchestrator, so the loop cannot miscount its own budget. Builder
spawns outside a /parrot:loop run get an implicit standalone counter with
the same cap.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parrot_common import debug_log, plugin_data_dir, plugin_option  # noqa: E402


def state_file(session: str) -> Path:
    safe = "".join(ch for ch in session if ch.isalnum() or ch in "-_") or "default"
    return plugin_data_dir() / "runs" / f"{safe}.json"


def main() -> int:
    payload = json.load(sys.stdin)
    debug_log(payload, "gate-agent-spawn")
    tool_input = payload.get("tool_input") or {}
    if tool_input.get("subagent_type") != "parrot:builder":
        return 0

    session = payload.get("session_id", "default")
    path = state_file(session)
    if path.exists():
        state = json.loads(path.read_text())
        if state.get("status") not in ("RUNNING", "STANDALONE"):
            # previous run reached a terminal status; builder used standalone afterwards
            state = {"status": "STANDALONE", "cycle": 0,
                     "max_cycles": plugin_option("max_cycles", 5),
                     "started_at": time.time()}
    else:
        state = {"status": "STANDALONE", "cycle": 0,
                 "max_cycles": plugin_option("max_cycles", 5),
                 "started_at": time.time()}

    max_cycles = int(state.get("max_cycles") or 5)
    if state.get("cycle", 0) >= max_cycles:
        print(
            f"parrot gate: builder dispatch #{state['cycle'] + 1} denied — the "
            f"{max_cycles}-cycle budget is spent. Write the escalation "
            "(parrot_state.py write-escalation), end the run, and hand this to "
            "a human. The stop rules are the product.",
            file=sys.stderr,
        )
        return 2

    state["cycle"] = state.get("cycle", 0) + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
