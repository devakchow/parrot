import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
AGENTS = Path(__file__).resolve().parent.parent / "agents"


def run_hook(script, payload, plugin_data):
    import os
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script)],
        input=json.dumps(payload), capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_DATA": str(plugin_data)},
    )


class TestFencedWriters:
    @pytest.mark.parametrize("agent", ["parrot:planner", "parrot:memory-codifier"])
    def test_edit_inside_parrot_allowed(self, plugin_data, agent):
        payload = {"agent_type": agent,
                   "tool_input": {"file_path": ".parrot/runs/x/plan.md"}}
        assert run_hook("guard-builder.py", payload, plugin_data).returncode == 0

    @pytest.mark.parametrize("agent", ["parrot:planner", "parrot:memory-codifier"])
    @pytest.mark.parametrize("path", [
        "CLAUDE.md", "src/app.py", "tests/test_app.py", "README.md",
    ])
    def test_edit_outside_parrot_denied(self, plugin_data, agent, path):
        payload = {"agent_type": agent, "tool_input": {"file_path": path}}
        result = run_hook("guard-builder.py", payload, plugin_data)
        assert result.returncode == 2
        assert ".parrot/" in result.stderr

    def test_bash_write_inside_parrot_allowed(self, plugin_data):
        payload = {"agent_type": "parrot:memory-codifier",
                   "tool_input": {"command": "echo 'learning' >> .parrot/learnings.md"}}
        assert run_hook("guard-bash.py", payload, plugin_data).returncode == 0

    @pytest.mark.parametrize("command", [
        "echo 'sneaky' >> CLAUDE.md",
        "tee src/app.py",
        "git add -A",
        "echo x > notes.md",
    ])
    def test_bash_write_outside_parrot_denied(self, plugin_data, command):
        payload = {"agent_type": "parrot:planner", "tool_input": {"command": command}}
        assert run_hook("guard-bash.py", payload, plugin_data).returncode == 2

    def test_reads_still_free(self, plugin_data):
        payload = {"agent_type": "parrot:planner",
                   "tool_input": {"command": "grep -rn 'def main' src/"}}
        assert run_hook("guard-bash.py", payload, plugin_data).returncode == 0


class TestReviewerContracts:
    def validate(self, plugin_data, agent, message, agent_id="r1"):
        payload = {"agent_type": agent, "session_id": "s1", "agent_id": agent_id,
                   "last_assistant_message": message}
        return run_hook("validate-report.py", payload, plugin_data)

    def test_spec_reviewer_valid(self, plugin_data):
        msg = "MISSING:\n- none\n\nUNREQUESTED:\n- none\n\nSPEC VERDICT: PASS"
        result = self.validate(plugin_data, "parrot:spec-reviewer", msg)
        assert result.returncode == 0 and not result.stdout.strip()

    def test_spec_reviewer_missing_verdict_blocked(self, plugin_data):
        msg = "Looks like everything matches the spec, nice work."
        out = json.loads(self.validate(plugin_data, "parrot:spec-reviewer", msg).stdout)
        assert out["decision"] == "block"
        assert "SPEC VERDICT" in out["reason"]

    def test_code_reviewer_valid_fail(self, plugin_data):
        msg = "FINDINGS:\n- src/app.py:10 — leaks handle — fd exhaustion\n\nREVIEW VERDICT: FAIL"
        result = self.validate(plugin_data, "parrot:code-reviewer", msg)
        assert result.returncode == 0 and not result.stdout.strip()

    def test_security_auditor_prose_blocked(self, plugin_data):
        out = json.loads(self.validate(
            plugin_data, "parrot:security-auditor", "No security issues!").stdout)
        assert out["decision"] == "block"
        assert "SECURITY VERDICT" in out["reason"]

    def test_reviewer_gives_up_after_retries(self, plugin_data):
        bad = "just prose"
        first = json.loads(self.validate(plugin_data, "parrot:code-reviewer", bad).stdout)
        assert first["decision"] == "block"
        second = json.loads(self.validate(plugin_data, "parrot:code-reviewer", bad).stdout)
        assert second["decision"] == "block"
        third = self.validate(plugin_data, "parrot:code-reviewer", bad)
        assert third.returncode == 0 and not third.stdout.strip()

    def test_checker_contract_still_enforced(self, plugin_data):
        out = json.loads(self.validate(plugin_data, "parrot:checker", "all good").stdout)
        assert out["decision"] == "block"


class TestAgentRoster:
    EXPECTED = {
        "builder", "checker", "planner", "spec-reviewer", "code-reviewer",
        "security-auditor", "memory-codifier",
    }
    READ_ONLY = {"checker", "spec-reviewer", "code-reviewer", "security-auditor"}

    def frontmatter(self, name):
        text = (AGENTS / f"{name}.md").read_text()
        body = text.split("---")[1]
        return dict(
            line.split(":", 1) for line in body.strip().splitlines() if ":" in line
        )

    def test_roster_complete(self):
        assert {p.stem for p in AGENTS.glob("*.md")} == self.EXPECTED

    def test_read_only_agents_have_no_edit_tools(self):
        for name in self.READ_ONLY:
            tools = self.frontmatter(name)["tools"]
            assert "Edit" not in tools and "Write" not in tools, name

    def test_all_agents_capped_and_colored(self):
        for name in self.EXPECTED:
            fm = self.frontmatter(name)
            assert int(fm["maxTurns"]) > 0, name
            assert fm["color"].strip() in {
                "red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan",
            }, name
