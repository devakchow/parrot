import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def run_hook(script, payload, plugin_data):
    import os
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        input=json.dumps(payload), capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_DATA": str(plugin_data)},
    )
    return result


def bash_payload(agent, command):
    return {"agent_type": agent, "session_id": "s1",
            "tool_input": {"command": command}}


class TestBuilderBashGuard:
    @pytest.mark.parametrize("command", [
        "sed -i 's/== 3/== 4/' tests/test_app.py",
        "sed -i.bak 's/x/y/' tests/test_app.py",
        "perl -i -pe 's/a/b/' spec/foo.spec.ts",
        "echo 'weakened' > tests/test_app.py",
        "cat evil.py >> tests/test_app.py",
        "echo x | tee tests/test_app.py",
        "rm tests/test_app.py",
        "rm -f tests/test_app.py",
        "mv tests/test_app.py /tmp/gone.py",
        "cp /tmp/weak.py tests/test_app.py",
        "touch conftest.py",
        "echo 'import sys' > conftest.py",
        "echo hack > src/conftest.py",
        "printf 'x' > sitecustomize.py",
        "git checkout -- tests/test_app.py",
        "git apply /tmp/weaken-tests.patch tests/test_app.py",
        "dd if=/dev/zero of=pyproject.toml",
        "echo '{}' > tsconfig.json",
        "sed -i 's/strict/loose/' pyproject.toml",
        "echo bad > .github/workflows/ci.yml",
        "echo x > .parrot/ledger.md",
    ])
    def test_denied(self, plugin_data, command):
        result = run_hook("guard-bash.py", bash_payload("parrot:builder", command), plugin_data)
        assert result.returncode == 2, f"should deny: {command}\n{result.stderr}"

    @pytest.mark.parametrize("command", [
        "ls -la",
        "cat tests/test_app.py",
        "git diff",
        "git status --porcelain",
        "grep -rn 'add' src/",
        "echo 'fixed' > src/app_helper.py",
        "sed -i 's/a/b/' src/app.py",
        "rm src/dead_code.py",
        "mkdir -p src/newmod",
        "python3 -c 'print(1)' 2>/dev/null",
        "pytest --collect-only > /dev/null 2>&1",
    ])
    def test_allowed(self, plugin_data, command):
        result = run_hook("guard-bash.py", bash_payload("parrot:builder", command), plugin_data)
        assert result.returncode == 0, f"should allow: {command}\n{result.stderr}"


class TestReadOnlyAgents:
    @pytest.mark.parametrize("agent", [
        "parrot:checker", "parrot:spec-reviewer", "parrot:code-reviewer",
        "parrot:security-auditor",
    ])
    @pytest.mark.parametrize("command", [
        "echo x > out.txt",
        "sed -i 's/a/b/' src/app.py",
        "rm anything.py",
        "tee capture.log",
        "git add -A",
        "git commit -m x",
        "git stash",
        "touch marker",
        "mkdir newdir",
    ])
    def test_writes_denied(self, plugin_data, agent, command):
        result = run_hook("guard-bash.py", bash_payload(agent, command), plugin_data)
        assert result.returncode == 2, f"{agent} should be denied: {command}"

    @pytest.mark.parametrize("command", [
        "pytest -q",
        "npx tsc --noEmit",
        "cargo test",
        "go test ./...",
        "git diff --name-only",
        "git status --porcelain",
        "pytest tests/test_app.py::test_add -q 2>&1",
        "npm test > /dev/null 2>&1",
        "cat CLAUDE.md",
    ])
    def test_checks_allowed(self, plugin_data, command):
        result = run_hook("guard-bash.py", bash_payload("parrot:checker", command), plugin_data)
        assert result.returncode == 0, f"checker should run: {command}\n{result.stderr}"


class TestOtherAgentsUntouched:
    def test_main_thread_free(self, plugin_data):
        result = run_hook("guard-bash.py", bash_payload("", "rm -rf tests/"), plugin_data)
        assert result.returncode == 0

    def test_foreign_agent_free(self, plugin_data):
        result = run_hook("guard-bash.py", bash_payload("Explore", "echo x > tests/t.py"), plugin_data)
        assert result.returncode == 0

    def test_edit_guard_ignores_foreign_agents(self, plugin_data):
        payload = {"agent_type": "other-plugin:writer",
                   "tool_input": {"file_path": "tests/test_app.py"}}
        result = run_hook("guard-builder.py", payload, plugin_data)
        assert result.returncode == 0
