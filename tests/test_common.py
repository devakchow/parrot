import pytest
from conftest import BASELINE_MIXED, GREEN_REPORT, RED_REPORT

from parrot_common import (
    classify_baseline,
    failure_signature,
    guarded_kind,
    normalize_error_text,
    parse_checker_report,
    signature_items,
)


class TestGuardedKind:
    @pytest.mark.parametrize("path,expected_fragment", [
        ("tests/test_app.py", "test"),
        ("src/__tests__/foo.ts", "test directory"),
        ("src/foo.test.ts", "test file"),
        ("src/foo.spec.js", "test file"),
        ("pkg/thing_test.go", "test file"),
        ("conftest.py", "harness hook"),
        ("src/deep/conftest.py", "harness hook"),
        ("sitecustomize.py", "harness hook"),
        ("usercustomize.py", "harness hook"),
        ("src/__snapshots__/foo.snap", "test directory"),
        ("components/Button.snap", "test file"),
        ("src/__mocks__/axios.js", "test directory"),
        ("tsconfig.json", "check configuration"),
        ("pyproject.toml", "check configuration"),
        (".eslintrc.js", "check configuration"),
        ("jest.config.ts", "check configuration"),
        (".github/workflows/ci.yml", "CI workflow"),
    ])
    def test_guarded(self, path, expected_fragment):
        kind = guarded_kind(path)
        assert kind is not None and expected_fragment in kind

    @pytest.mark.parametrize("path", [
        "src/app.py", "README.md", "src/attestation.py", "package.json",
        "src/protests/rally.py",  # 'protests' is not a test dir segment
        "docs/latest/notes.md", "",
    ])
    def test_unguarded(self, path):
        assert guarded_kind(path) is None

    @pytest.mark.parametrize("path", [
        "tests/__pycache__/test_app.cpython-312-pytest-7.4.4.pyc",
        "tests/test_app.pyc",
        ".pytest_cache/v/cache/lastfailed",
        "tests/.mypy_cache/3.12/app.data.json",
    ])
    def test_generated_caches_never_guarded(self, path):
        # caches churn on every test run; guarding them would fire false tamper
        assert guarded_kind(path) is None


class TestParser:
    def test_green_round_trip(self):
        report = parse_checker_report(GREEN_REPORT)
        assert report.valid, report.problems
        assert report.verdict == "GREEN"
        assert report.changed_files == ["app.py"]
        assert report.inventory["total"] == 10
        assert [c["status"] for c in report.checks] == ["PASS", "PASS"]
        assert report.tamper_signals == []

    def test_red_round_trip(self):
        report = parse_checker_report(RED_REPORT)
        assert report.valid, report.problems
        assert report.verdict == "RED"
        assert report.check_status("pytest") == "FAIL"
        assert "AssertionError" in report.failures["pytest"]

    def test_missing_sections_flagged(self):
        report = parse_checker_report("VERDICT: GREEN\n")
        assert not report.valid
        assert any("CHANGED FILES" in p for p in report.problems)
        assert any("TEST INVENTORY" in p for p in report.problems)
        assert any("TAMPER SIGNALS" in p for p in report.problems)

    def test_green_with_fail_check_contradiction(self):
        text = RED_REPORT.replace("VERDICT: RED", "VERDICT: GREEN")
        report = parse_checker_report(text)
        assert any("contradicts" in p for p in report.problems)

    def test_fail_without_failure_block(self):
        text = GREEN_REPORT.replace(
            "- pytest (pytest -q): PASS", "- pytest (pytest -q): FAIL"
        ).replace("VERDICT: GREEN", "VERDICT: RED")
        report = parse_checker_report(text)
        assert any("no FAILURES block" in p for p in report.problems)

    def test_bad_verdict(self):
        report = parse_checker_report(GREEN_REPORT.replace("VERDICT: GREEN", "VERDICT: MAYBE"))
        assert any("VERDICT must be" in p for p in report.problems)

    def test_tamper_signals_parsed(self):
        text = GREEN_REPORT.replace(
            "TAMPER SIGNALS:\n- none",
            "TAMPER SIGNALS:\n- new conftest.py created at src/conftest.py",
        )
        report = parse_checker_report(text)
        assert report.tamper_signals == ["new conftest.py created at src/conftest.py"]

    def test_empty_input(self):
        report = parse_checker_report("")
        assert not report.valid


class TestSignature:
    def test_noise_stripped(self):
        noisy = "Error at 0x7fff5fbff8c0 in /tmp/pytest-123/x.py at 2026-07-02T10:11:12 in 0.32s"
        cleaned = normalize_error_text(noisy)
        assert "0x7fff" not in cleaned
        assert "/tmp/pytest-123" not in cleaned
        assert "2026-07-02" not in cleaned
        assert "0.32s" not in cleaned

    def test_signature_stable_under_noise(self):
        a = parse_checker_report(RED_REPORT)
        noisy = RED_REPORT.replace(
            "AssertionError: assert 4 == 3",
            "AssertionError: assert 4 == 3 at 0xdeadbeef in 1.5s",
        )
        b = parse_checker_report(noisy)
        assert failure_signature(a) == failure_signature(b)

    def test_signature_changes_with_failure_set(self):
        a = parse_checker_report(RED_REPORT)
        different = RED_REPORT.replace("test_add", "test_subtract")
        b = parse_checker_report(different)
        assert failure_signature(a) != failure_signature(b)

    def test_items_extract_pytest_id_and_class(self):
        report = parse_checker_report(RED_REPORT)
        items = signature_items(report)
        assert ("pytest", "tests/test_app.py::test_add", "AssertionError") in items

    def test_go_and_cargo_ids(self):
        text = RED_REPORT.replace(
            "FAILED tests/test_app.py::test_add - AssertionError: assert 4 == 3",
            "--- FAIL: TestAdd\ntest util::sums ... FAILED",
        )
        items = signature_items(parse_checker_report(text))
        ids = {item[1] for item in items}
        assert "TestAdd" in ids and "util::sums" in ids

    def test_unparseable_failure_falls_back_to_text_hash(self):
        text = RED_REPORT.replace(
            "FAILED tests/test_app.py::test_add - AssertionError: assert 4 == 3",
            "some completely unstructured failure output",
        )
        items = signature_items(parse_checker_report(text))
        assert len(items) == 1 and items[0][2].startswith("text:")


class TestClassifyBaseline:
    def test_mixed(self):
        baseline = classify_baseline(parse_checker_report(BASELINE_MIXED))
        assert baseline["targets"] == ["pytest"]
        assert sorted(baseline["protected"]) == ["lint", "mypy"]
        assert baseline["flaky"] == []

    def test_flaky_excluded_from_both(self):
        text = BASELINE_MIXED.replace("- lint (ruff check): PASS", "- lint (ruff check): FLAKY")
        baseline = classify_baseline(parse_checker_report(text))
        assert "lint" not in baseline["targets"]
        assert "lint" not in baseline["protected"]
        assert baseline["flaky"] == ["lint"]
