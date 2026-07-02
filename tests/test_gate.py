import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def spawn(plugin_data, session="s1", subagent="parrot:builder", env_extra=None):
    import os
    payload = {"session_id": session, "tool_input": {"subagent_type": subagent}}
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "gate-agent-spawn.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_DATA": str(plugin_data), **(env_extra or {})},
    )


def state_of(plugin_data, session="s1"):
    return json.loads((plugin_data / "runs" / f"{session}.json").read_text())


class TestSpawnGate:
    def test_sixth_spawn_denied(self, plugin_data):
        for n in range(5):
            assert spawn(plugin_data).returncode == 0, f"spawn {n + 1} should pass"
        result = spawn(plugin_data)
        assert result.returncode == 2
        assert "budget is spent" in result.stderr

    def test_counter_in_state(self, plugin_data):
        spawn(plugin_data)
        spawn(plugin_data)
        assert state_of(plugin_data)["cycle"] == 2

    def test_sessions_isolated(self, plugin_data):
        for _ in range(5):
            spawn(plugin_data, session="a")
        assert spawn(plugin_data, session="a").returncode == 2
        assert spawn(plugin_data, session="b").returncode == 0

    def test_non_builder_spawns_ignored(self, plugin_data):
        for _ in range(10):
            assert spawn(plugin_data, subagent="parrot:checker").returncode == 0
        assert spawn(plugin_data, subagent="Explore").returncode == 0

    def test_respects_run_state_from_init_run(self, plugin_data, project, state_cli):
        state_cli("init-run", "--session", "s1", "--project", str(project),
                  "--max-cycles", "2", stdin="task")
        assert spawn(plugin_data).returncode == 0
        assert spawn(plugin_data).returncode == 0
        assert spawn(plugin_data).returncode == 2
        # loop state fields survive the gate's writes
        state = state_of(plugin_data)
        assert state["status"] == "RUNNING" and state["cycle"] == 2

    def test_terminal_run_resets_to_standalone(self, plugin_data, project, state_cli):
        state_cli("init-run", "--session", "s1", "--project", str(project),
                  "--max-cycles", "1", stdin="task")
        assert spawn(plugin_data).returncode == 0
        assert spawn(plugin_data).returncode == 2
        state_cli("end-run", "--session", "s1", "--status", "MAX-CYCLES-HALT")
        result = spawn(plugin_data)  # fresh standalone counter after run ended
        assert result.returncode == 0
        assert state_of(plugin_data)["status"] == "STANDALONE"

    def test_max_cycles_env_override(self, plugin_data):
        env = {"CLAUDE_PLUGIN_OPTION_MAX_CYCLES": "1"}
        assert spawn(plugin_data, env_extra=env).returncode == 0
        assert spawn(plugin_data, env_extra=env).returncode == 2


class TestValidateReport:
    def run_validator(self, plugin_data, message, agent_id="a1"):
        import os
        payload = {"agent_type": "parrot:checker", "session_id": "s1",
                   "agent_id": agent_id, "last_assistant_message": message}
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "validate-report.py")],
            input=json.dumps(payload), capture_output=True, text=True,
            env={**os.environ, "CLAUDE_PLUGIN_DATA": str(plugin_data)},
        )

    def test_valid_report_passes(self, plugin_data):
        from conftest import GREEN_REPORT
        result = self.run_validator(plugin_data, GREEN_REPORT)
        assert result.returncode == 0 and not result.stdout.strip()

    def test_invalid_report_blocked_with_contract(self, plugin_data):
        result = self.run_validator(plugin_data, "All checks passed, looks great!")
        out = json.loads(result.stdout)
        assert out["decision"] == "block"
        assert "VERDICT" in out["reason"]

    def test_gives_up_after_two_retries(self, plugin_data):
        bad = "not a report"
        assert json.loads(self.run_validator(plugin_data, bad).stdout)["decision"] == "block"
        assert json.loads(self.run_validator(plugin_data, bad).stdout)["decision"] == "block"
        third = self.run_validator(plugin_data, bad)
        assert third.returncode == 0 and not third.stdout.strip()

    def test_fail_open_without_message(self, plugin_data):
        import os
        payload = {"agent_type": "parrot:checker", "session_id": "s1"}
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate-report.py")],
            input=json.dumps(payload), capture_output=True, text=True,
            env={**os.environ, "CLAUDE_PLUGIN_DATA": str(plugin_data)},
        )
        assert result.returncode == 0 and not result.stdout.strip()

    def test_foreign_agent_ignored(self, plugin_data):
        import os
        payload = {"agent_type": "other:agent", "session_id": "s1",
                   "last_assistant_message": "gibberish"}
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate-report.py")],
            input=json.dumps(payload), capture_output=True, text=True,
            env={**os.environ, "CLAUDE_PLUGIN_DATA": str(plugin_data)},
        )
        assert result.returncode == 0


class TestInjectContext:
    def run_injector(self, plugin_data, agent="parrot:builder", session="s1"):
        import os
        payload = {"agent_type": agent, "session_id": session}
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "inject-context.py")],
            input=json.dumps(payload), capture_output=True, text=True,
            env={**os.environ, "CLAUDE_PLUGIN_DATA": str(plugin_data)},
        )

    def test_injects_baseline_and_cycle(self, plugin_data, project, state_cli):
        from conftest import BASELINE_MIXED
        state_cli("init-run", "--session", "s1", "--project", str(project), stdin="t")
        state_cli("record-baseline", "--session", "s1", stdin=BASELINE_MIXED)
        out = json.loads(self.run_injector(plugin_data).stdout)
        context = out["hookSpecificOutput"]["additionalContext"]
        assert "protected checks" in context and "mypy" in context
        assert "cycle: 0 of 5" in context

    def test_silent_without_state(self, plugin_data):
        result = self.run_injector(plugin_data, session="nope")
        assert result.returncode == 0 and not result.stdout.strip()

    def test_foreign_agent_ignored(self, plugin_data):
        result = self.run_injector(plugin_data, agent="Explore")
        assert result.returncode == 0 and not result.stdout.strip()
