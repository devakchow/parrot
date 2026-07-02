#!/usr/bin/env python3
"""parrot session banner: SessionStart hook (startup).

Shows a green parrot and a one-line intro to the user when the plugin loads.
Color drops out under NO_COLOR (https://no-color.org/).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parrot_common import debug_log  # noqa: E402

GREEN = "\033[92m"
RESET = "\033[0m"

ART = [" __", "(o>", "//\\", "V_/_"]


def banner(version: str, color: bool) -> str:
    g, r = (GREEN, RESET) if color else ("", "")
    intro = [
        f"parrot v{version} — your hired engineering team",
        "builder/checker loop with hook-enforced guardrails and tamper-proof verification",
        "/parrot:hire · /parrot:loop · /parrot:verify · /parrot:review",
        "",
    ]
    return "\n".join(f"{g}{a:<4}{r}  {t}".rstrip() for a, t in zip(ART, intro))


def main() -> int:
    payload = json.load(sys.stdin)
    debug_log(payload, "session-banner")
    manifest = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
    version = json.loads(manifest.read_text())["version"]
    color = not os.environ.get("NO_COLOR")
    print(json.dumps({"systemMessage": banner(version, color)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
