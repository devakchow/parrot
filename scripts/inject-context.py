#!/usr/bin/env python3
"""parrot context injector: SubagentStart hook on ^parrot: agents.

Injects ground truth (cycle number, baseline classification, run dir,
active profile rubric) straight from the state file into every parrot
agent, so the loop's facts reach the agents even if the orchestrator's
prompt assembly drifts. Belt-and-suspenders: the loop still works when
this injects nothing.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parrot_common import debug_log, plugin_data_dir  # noqa: E402


def main() -> int:
    payload = json.load(sys.stdin)
    debug_log(payload, "inject-context")
    agent = payload.get("agent_type", "")
    if not agent.startswith("parrot:"):
        return 0
    session = payload.get("session_id", "default")
    safe = "".join(ch for ch in session if ch.isalnum() or ch in "-_") or "default"
    path = plugin_data_dir() / "runs" / f"{safe}.json"
    if not path.exists():
        return 0
    try:
        state = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return 0
    if state.get("status") != "RUNNING":
        return 0

    lines = [
        "[parrot ground truth — injected by hook from run state]",
        f"cycle: {state.get('cycle', 0)} of {state.get('max_cycles', 5)}",
        f"run artifacts: {state.get('run_dir', '?')}",
        f"guarded files in task scope (--allow-guarded): {state.get('allow_guarded', False)}",
    ]
    baseline = state.get("baseline")
    if baseline:
        lines.append(f"protected checks (regression if these fail): {', '.join(baseline.get('protected', [])) or 'none'}")
        lines.append(f"target checks (failing at baseline): {', '.join(baseline.get('targets', [])) or 'none'}")
        inventory = baseline.get("inventory") or {}
        if inventory:
            lines.append("baseline test inventory: " + " | ".join(f"{k}: {v}" for k, v in inventory.items()))
        dirty = baseline.get("changed_files") or []
        if dirty:
            lines.append(f"pre-existing dirty files (not the builder's doing): {', '.join(dirty)}")
    profile = state.get("profile")
    if profile:
        lines.append(f"active profile: {profile.get('name', '?')}")
        rubric = profile.get("rubrics", {}).get(agent.split(":", 1)[1])
        if rubric:
            lines.append("profile rubric for this role:\n" + rubric)

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SubagentStart",
            "additionalContext": "\n".join(lines),
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
