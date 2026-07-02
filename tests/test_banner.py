import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def run_banner(payload, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "session-banner.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env={k: v for k, v in {**os.environ, **(env or {})}.items() if v is not None},
    )


class TestSessionBanner:
    def test_green_parrot_and_intro(self):
        result = run_banner({"cwd": "/tmp"}, env={"NO_COLOR": None})
        assert result.returncode == 0
        msg = json.loads(result.stdout)["systemMessage"]
        assert "(o>" in msg
        assert "\033[92m" in msg
        assert "parrot v" in msg
        assert "/parrot:hire" in msg

    def test_no_color_strips_ansi(self):
        result = run_banner({}, env={"NO_COLOR": "1"})
        assert result.returncode == 0
        msg = json.loads(result.stdout)["systemMessage"]
        assert "\033[" not in msg
        assert "(o>" in msg

    def test_version_matches_manifest(self):
        manifest = SCRIPTS.parent / ".claude-plugin" / "plugin.json"
        version = json.loads(manifest.read_text())["version"]
        result = run_banner({})
        msg = json.loads(result.stdout)["systemMessage"]
        assert f"parrot v{version}" in msg
