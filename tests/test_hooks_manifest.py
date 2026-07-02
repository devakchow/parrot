"""Every hook registered in hooks/hooks.json must be directly invocable.

The hook runner executes the command string via the shell, so a script
without the exec bit fails with 126 Permission denied — silently disabling
enforcement (found live: session-nudge, guard-bash, gate-agent-spawn,
inject-context, validate-report all shipped 644).
"""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def registered_hook_scripts():
    manifest = json.loads((ROOT / "hooks" / "hooks.json").read_text())
    for event_hooks in manifest["hooks"].values():
        for entry in event_hooks:
            for hook in entry["hooks"]:
                match = re.search(r"scripts/([\w.-]+\.py)", hook["command"])
                assert match, f"unrecognized hook command: {hook['command']}"
                yield ROOT / "scripts" / match.group(1)


def test_hook_scripts_exist_executable_with_shebang():
    scripts = list(registered_hook_scripts())
    assert scripts, "no hook scripts registered in hooks.json"
    for script in scripts:
        assert script.exists(), f"{script} missing"
        assert os.access(script, os.X_OK), (
            f"{script.name} lacks exec bit: hook runner fails with 126"
        )
        assert script.read_text().startswith("#!/usr/bin/env python3"), (
            f"{script.name} missing python3 shebang"
        )
