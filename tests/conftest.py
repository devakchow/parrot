import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def plugin_data(tmp_path, monkeypatch):
    data = tmp_path / "plugin-data"
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data))
    return data


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-C", str(repo), *args], check=True, capture_output=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "HOME": str(tmp_path),
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"},
    )
    git("init", "-q")
    (repo / "app.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_app.py").write_text(
        "from app import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    )
    (repo / "pyproject.toml").write_text("[project]\nname = 'toy'\n")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    return repo


def run_state(plugin_data, *args, stdin=""):
    """Invoke parrot_state.py as the CLI it is; returns parsed stdout JSON."""
    import json
    import os

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "parrot_state.py"), *args],
        input=stdin, capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PLUGIN_DATA": str(plugin_data)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture
def state_cli(plugin_data):
    return lambda *args, stdin="": run_state(plugin_data, *args, stdin=stdin)


GREEN_REPORT = """\
CHANGED FILES:
app.py

TEST INVENTORY:
total: 10 | passed: 10 | failed: 0 | skipped: 0 | xfail: 0

CHECKS:
- pytest (pytest -q): PASS
- mypy (mypy .): PASS

TAMPER SIGNALS:
- none

FAILURES:

VERDICT: GREEN
"""

RED_REPORT = """\
CHANGED FILES:
app.py

TEST INVENTORY:
total: 10 | passed: 9 | failed: 1 | skipped: 0 | xfail: 0

CHECKS:
- pytest (pytest -q): FAIL
- mypy (mypy .): PASS

TAMPER SIGNALS:
- none

FAILURES:
### pytest
locus: app.py:2
repro: pytest tests/test_app.py::test_add -q
FAILED tests/test_app.py::test_add - AssertionError: assert 4 == 3

VERDICT: RED
"""

BASELINE_MIXED = """\
CHANGED FILES:
none

TEST INVENTORY:
total: 10 | passed: 9 | failed: 1 | skipped: 0 | xfail: 0

CHECKS:
- pytest (pytest -q): FAIL
- mypy (mypy .): PASS
- lint (ruff check): PASS

TAMPER SIGNALS:
- none

FAILURES:
### pytest
locus: app.py:2
repro: pytest tests/test_app.py::test_add -q
FAILED tests/test_app.py::test_add - AssertionError: assert 4 == 3

VERDICT: RED
"""
