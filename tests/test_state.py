import json
from pathlib import Path

from conftest import BASELINE_MIXED, GREEN_REPORT, RED_REPORT


def init_run(state_cli, project, **kw):
    args = ["init-run", "--session", kw.get("session", "sess-1"),
            "--project", str(project)]
    if kw.get("allow_guarded"):
        args.append("--allow-guarded")
    return state_cli(*args, stdin=kw.get("task", "fix the adder"))


class TestInitRun:
    def test_creates_run_dir_and_state(self, state_cli, project, plugin_data):
        out = init_run(state_cli, project)
        run_dir = Path(out["run_dir"])
        assert run_dir.is_dir() and ".parrot" in run_dir.parts
        assert (run_dir / "task.md").read_text().strip() == "fix the adder"
        assert (project / ".parrot" / ".gitignore").read_text() == "runs/\n"
        state = json.loads((plugin_data / "runs" / "sess-1.json").read_text())
        assert state["cycle"] == 0 and state["max_cycles"] == 5

    def test_sessions_isolated(self, state_cli, project):
        a = init_run(state_cli, project, session="sess-a")
        b = init_run(state_cli, project, session="sess-b")
        assert a["run_dir"] != b["run_dir"]
        state_a = state_cli("get-state", "--session", "sess-a")
        assert state_a["run_id"] == a["run_id"]


class TestBaselineAndIntegrity:
    def test_baseline_classifies(self, state_cli, project):
        init_run(state_cli, project)
        out = state_cli("record-baseline", "--session", "sess-1", stdin=BASELINE_MIXED)
        assert out["status"] == "BASELINE-RECORDED"
        assert out["targets"] == ["pytest"]
        assert sorted(out["protected"]) == ["lint", "mypy"]

    def test_integrity_pass_when_untouched(self, state_cli, project):
        init_run(state_cli, project)
        state_cli("snapshot-integrity", "--session", "sess-1")
        out = state_cli("verify-integrity", "--session", "sess-1")
        assert out["status"] == "PASS"

    def test_integrity_catches_bash_style_tamper(self, state_cli, project):
        init_run(state_cli, project)
        state_cli("snapshot-integrity", "--session", "sess-1")
        # what a sed -i bypass of the Edit guard looks like
        test_file = project / "tests" / "test_app.py"
        test_file.write_text(test_file.read_text().replace("== 3", "== 4"))
        out = state_cli("verify-integrity", "--session", "sess-1")
        assert out["status"] == "FAIL"
        assert out["modified"] == ["tests/test_app.py"]

    def test_integrity_catches_new_conftest(self, state_cli, project):
        init_run(state_cli, project)
        state_cli("snapshot-integrity", "--session", "sess-1")
        (project / "conftest.py").write_text("import sys\n")
        out = state_cli("verify-integrity", "--session", "sess-1")
        assert out["status"] == "FAIL"
        assert out["added"] == ["conftest.py"]

    def test_allow_guarded_downgrades_to_advisory(self, state_cli, project):
        init_run(state_cli, project, allow_guarded=True)
        state_cli("snapshot-integrity", "--session", "sess-1")
        (project / "tests" / "test_app.py").write_text("def test_new(): pass\n")
        out = state_cli("verify-integrity", "--session", "sess-1")
        assert out["status"] == "ADVISORY"


class TestRecordVerdict:
    def setup_run(self, state_cli, project):
        init_run(state_cli, project)
        state_cli("record-baseline", "--session", "sess-1", stdin=BASELINE_MIXED)

    def test_green_candidate(self, state_cli, project):
        self.setup_run(state_cli, project)
        out = state_cli("record-verdict", "--session", "sess-1", stdin=GREEN_REPORT)
        assert out["status"] == "GREEN-CANDIDATE"

    def test_progress_then_stalled(self, state_cli, project):
        self.setup_run(state_cli, project)
        first = state_cli("record-verdict", "--session", "sess-1", stdin=RED_REPORT)
        assert first["status"] == "PROGRESS"
        second = state_cli("record-verdict", "--session", "sess-1", stdin=RED_REPORT)
        assert second["status"] == "STALLED"

    def test_regression_on_protected_check(self, state_cli, project):
        self.setup_run(state_cli, project)
        regressed = RED_REPORT.replace("- mypy (mypy .): PASS", "- mypy (mypy .): FAIL") \
                              .replace("FAILURES:", "FAILURES:\n### mypy\nlocus: app.py:1\nrepro: mypy app.py\napp.py:1: error: bad type\n")
        out = state_cli("record-verdict", "--session", "sess-1", stdin=regressed)
        assert out["status"] == "REGRESSION"
        assert out["regressions"] == ["mypy"]

    def test_target_failing_is_not_regression(self, state_cli, project):
        self.setup_run(state_cli, project)
        out = state_cli("record-verdict", "--session", "sess-1", stdin=RED_REPORT)
        assert out["status"] == "PROGRESS"
        assert out["regressions"] == []

    def test_flaky_protected_is_not_regression(self, state_cli, project):
        self.setup_run(state_cli, project)
        flaky = RED_REPORT.replace("- mypy (mypy .): PASS", "- mypy (mypy .): FLAKY")
        out = state_cli("record-verdict", "--session", "sess-1", stdin=flaky)
        assert out["status"] == "PROGRESS"
        assert out["flaky"] == ["mypy"]

    def test_tamper_signal_wins(self, state_cli, project):
        self.setup_run(state_cli, project)
        tampered = GREEN_REPORT.replace(
            "TAMPER SIGNALS:\n- none",
            "TAMPER SIGNALS:\n- sys.exit(0) added in app.py",
        )
        out = state_cli("record-verdict", "--session", "sess-1", stdin=tampered)
        assert out["status"] == "TAMPER"

    def test_invalid_report_flagged(self, state_cli, project):
        self.setup_run(state_cli, project)
        out = state_cli("record-verdict", "--session", "sess-1", stdin="VERDICT: GREEN")
        assert out["status"] == "INVALID-REPORT"
        assert out["problems"]

    def test_verdict_files_written(self, state_cli, project):
        self.setup_run(state_cli, project)
        state_cli("record-verdict", "--session", "sess-1", stdin=RED_REPORT)
        state_cli("record-verdict", "--session", "sess-1", stdin=GREEN_REPORT)
        state = state_cli("get-state", "--session", "sess-1")
        run_dir = Path(state["run_dir"])
        assert (run_dir / "verdict-1.md").exists()
        assert (run_dir / "verdict-2.md").exists()


class TestLedgerEscalationEnd:
    def test_ledger_appends_with_cycle_headers(self, state_cli, project):
        init_run(state_cli, project)
        state_cli("append-ledger", "--session", "sess-1", "--cycle", "1",
                  stdin="attempted: fix add\nresult: RED\nruled out: off-by-one")
        state_cli("append-ledger", "--session", "sess-1", "--cycle", "2",
                  stdin="attempted: rewrite\nresult: GREEN")
        state = state_cli("get-state", "--session", "sess-1")
        ledger = (Path(state["run_dir"]) / "ledger.md").read_text()
        assert "## Cycle 1" in ledger and "## Cycle 2" in ledger
        assert ledger.index("## Cycle 1") < ledger.index("## Cycle 2")

    def test_escalation_and_end_run(self, state_cli, project):
        init_run(state_cli, project)
        state_cli("write-escalation", "--session", "sess-1",
                  stdin="blockers: spec conflict\nconfidence: low")
        out = state_cli("end-run", "--session", "sess-1", "--status", "STALLED-HALT")
        assert out["status"] == "STALLED-HALT"
        state = state_cli("get-state", "--session", "sess-1")
        assert (Path(state["run_dir"]) / "escalation.md").exists()
        assert (Path(state["run_dir"]) / "status").read_text().strip() == "STALLED-HALT"
