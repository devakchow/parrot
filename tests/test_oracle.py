import json
import os
import stat
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def run_oracle(plugin_data, stdin="why does it fail?", extra_env=None, path_prefix=None):
    env = {**os.environ, "CLAUDE_PLUGIN_DATA": str(plugin_data), **(extra_env or {})}
    if path_prefix:
        env["PATH"] = f"{path_prefix}:{env['PATH']}"
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "oracle.py")],
        input=stdin, capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


class TestOracle:
    def test_disabled_by_default(self, plugin_data):
        assert run_oracle(plugin_data).startswith("ORACLE: disabled")

    def test_enabled_but_no_cli(self, plugin_data, tmp_path):
        empty = tmp_path / "emptybin"
        empty.mkdir()
        out = run_oracle(
            plugin_data,
            extra_env={"CLAUDE_PLUGIN_OPTION_ORACLE_ENABLED": "true",
                       "PATH": str(empty)},
        )
        assert out.startswith("ORACLE: unavailable")

    def test_enabled_with_fake_codex(self, plugin_data, tmp_path):
        fakebin = tmp_path / "fakebin"
        fakebin.mkdir()
        fake = fakebin / "codex"
        fake.write_text("#!/bin/sh\necho \"second opinion: check the fixture\"\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        out = run_oracle(
            plugin_data,
            extra_env={"CLAUDE_PLUGIN_OPTION_ORACLE_ENABLED": "true"},
            path_prefix=str(fakebin),
        )
        assert out.startswith("ORACLE (codex):")
        assert "second opinion" in out

    def test_failing_cli_degrades(self, plugin_data, tmp_path):
        fakebin = tmp_path / "fakebin"
        fakebin.mkdir()
        fake = fakebin / "codex"
        fake.write_text("#!/bin/sh\nexit 3\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        out = run_oracle(
            plugin_data,
            extra_env={"CLAUDE_PLUGIN_OPTION_ORACLE_ENABLED": "true"},
            path_prefix=str(fakebin),
        )
        assert "exited 3" in out and "advisory skipped" in out

    def test_config_json_enables(self, plugin_data):
        plugin_data.mkdir(parents=True, exist_ok=True)
        (plugin_data / "config.json").write_text(json.dumps({"oracle_enabled": True}))
        out = run_oracle(plugin_data, extra_env={"PATH": "/nonexistent"})
        assert out.startswith("ORACLE: unavailable")


class TestCandidates:
    def setup_clean_run(self, state_cli, project):
        from conftest import GREEN_REPORT
        baseline = GREEN_REPORT.replace("CHANGED FILES:\napp.py", "CHANGED FILES:\nnone")
        state_cli("init-run", "--session", "s1", "--project", str(project), stdin="t")
        state_cli("record-baseline", "--session", "s1", stdin=baseline)

    def test_save_and_restore_winner(self, state_cli, project):
        self.setup_clean_run(state_cli, project)
        app = project / "app.py"

        app.write_text("def add(a, b):\n    return a + b  # candidate A\n")
        out_a = state_cli("save-candidate", "--session", "s1", "--label", "A")
        assert out_a["status"] == "SAVED"
        assert "candidate A" not in app.read_text()  # tree reset after stash

        app.write_text("def add(a, b):\n    return b + a  # candidate B\n")
        assert state_cli("save-candidate", "--session", "s1", "--label", "B")["status"] == "SAVED"

        out = state_cli("restore-candidate", "--session", "s1", "--label", "A")
        assert out["status"] == "RESTORED"
        assert "candidate A" in app.read_text()
        stashes = subprocess.run(
            ["git", "-C", str(project), "stash", "list"],
            capture_output=True, text=True,
        ).stdout
        assert "parrot-cand" not in stashes  # losers dropped

    def test_patch_artifacts_written(self, state_cli, project):
        self.setup_clean_run(state_cli, project)
        (project / "app.py").write_text("def add(a, b):\n    return a + b + 0\n")
        state_cli("save-candidate", "--session", "s1", "--label", "A")
        state = state_cli("get-state", "--session", "s1")
        patch = Path(state["run_dir"]) / "candidates" / "A.patch"
        assert patch.exists() and "app.py" in patch.read_text()

    def test_dirty_baseline_unsupported(self, state_cli, project):
        from conftest import GREEN_REPORT  # baseline reports app.py as pre-dirty
        state_cli("init-run", "--session", "s2", "--project", str(project), stdin="t")
        state_cli("record-baseline", "--session", "s2", stdin=GREEN_REPORT)
        out = state_cli("save-candidate", "--session", "s2", "--label", "A")
        assert out["status"] == "UNSUPPORTED"
