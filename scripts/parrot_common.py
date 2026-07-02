"""parrot shared core: guarded-path classification, checker-report parsing,
failure-signature normalization, baseline classification.

Single source of truth consumed by the guard hooks, the state CLI, and the
report validator, so enforcement points cannot drift apart. Stdlib only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import PurePath
from typing import Optional

# ---------------------------------------------------------------------------
# Guarded-path classification
# ---------------------------------------------------------------------------

TEST_DIR_SEGMENTS = {"test", "tests", "__tests__", "spec", "specs", "__snapshots__", "__mocks__"}
TEST_FILE_GLOBS = (
    "*.test.*", "*.spec.*", "*_test.*", "test_*.py", "conftest.py", "*.snap",
)
# Interpreter/runner hook files: creating one anywhere lets code run inside the
# test harness itself (the documented conftest.py/sitecustomize.py hack class).
HARNESS_HOOK_FILES = ("conftest.py", "sitecustomize.py", "usercustomize.py")
CHECK_CONFIG_GLOBS = (
    ".eslintrc*", "eslint.config.*", "tsconfig*.json", "jest.config.*",
    "vitest.config.*", "playwright.config.*", "cypress.config.*", "karma.conf.*",
    "biome.json*", "pytest.ini", "mypy.ini", ".flake8", "ruff.toml", ".ruff.toml",
    "setup.cfg", "pyproject.toml", ".golangci.*", ".rubocop.yml", "phpunit.xml*",
)


def guarded_kind(path_str: str) -> Optional[str]:
    """Classify a path as guarded (test file / harness hook / check config) or None."""
    if not path_str:
        return None
    path = PurePath(path_str)
    name = path.name
    if name in HARNESS_HOOK_FILES:
        return "a test-harness hook file"
    if any(part.lower() in TEST_DIR_SEGMENTS for part in path.parts[:-1]):
        return "a file in a test directory"
    if any(fnmatch(name, glob) for glob in TEST_FILE_GLOBS):
        return "a test file"
    if any(fnmatch(name, glob) for glob in CHECK_CONFIG_GLOBS):
        return "check configuration"
    parts_lower = [p.lower() for p in path.parts[:-1]]
    if ".github" in parts_lower and "workflows" in parts_lower:
        return "CI workflow configuration"
    return None


# ---------------------------------------------------------------------------
# Checker report contract v2
# ---------------------------------------------------------------------------

VERDICTS = ("GREEN", "RED")
CHECK_STATUSES = ("PASS", "FAIL", "FLAKY")

REPORT_CONTRACT = """\
CHANGED FILES:
<output of git diff --name-only, plus untracked files; or "none">

TEST INVENTORY:
total: <n> | passed: <n> | failed: <n> | skipped: <n> | xfail: <n>

CHECKS:
- <check-name> (<command>): PASS | FAIL | FLAKY

TAMPER SIGNALS:
- none            (or one line per signal found)

FAILURES:
### <check-name>
locus: <file:line of root cause, or "unknown">
repro: <minimal single-failure command>
<exact error output, trimmed to relevant lines>

VERDICT: GREEN | RED
"""

_SECTION_RE = re.compile(
    r"^(CHANGED FILES|TEST INVENTORY|CHECKS|TAMPER SIGNALS|FAILURES|VERDICT):",
    re.MULTILINE,
)
_CHECK_LINE_RE = re.compile(r"^- (.+?) \((.+)\): (PASS|FAIL|FLAKY)\s*$", re.MULTILINE)
_INVENTORY_PAIR_RE = re.compile(r"(total|passed|failed|skipped|xfail)\s*:\s*(\d+)")
_FAILURE_BLOCK_RE = re.compile(r"^### (.+?)\s*$", re.MULTILINE)


@dataclass
class CheckerReport:
    changed_files: list = field(default_factory=list)
    inventory: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)  # [{name, command, status}]
    tamper_signals: list = field(default_factory=list)
    failures: dict = field(default_factory=dict)  # check-name -> block text
    verdict: str = ""
    problems: list = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.problems

    def check_status(self, name: str) -> Optional[str]:
        for c in self.checks:
            if c["name"] == name:
                return c["status"]
        return None


def _split_sections(text: str) -> dict:
    sections: dict = {}
    matches = list(_SECTION_RE.finditer(text))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip("\n")
        sections[m.group(1)] = body
    return sections


def parse_checker_report(text: str) -> CheckerReport:
    """Parse the v2 checker report. Never raises; problems list carries violations."""
    report = CheckerReport()
    sections = _split_sections(text or "")

    required = ("CHANGED FILES", "TEST INVENTORY", "CHECKS", "TAMPER SIGNALS", "VERDICT")
    for name in required:
        if name not in sections:
            report.problems.append(f"missing section: {name}:")

    changed = sections.get("CHANGED FILES", "")
    report.changed_files = [
        line.strip() for line in changed.splitlines()
        if line.strip() and line.strip().lower() != "none"
    ]

    for key, val in _INVENTORY_PAIR_RE.findall(sections.get("TEST INVENTORY", "")):
        report.inventory[key] = int(val)

    checks_body = sections.get("CHECKS", "")
    for name, command, status in _CHECK_LINE_RE.findall(checks_body):
        report.checks.append({"name": name.strip(), "command": command.strip(), "status": status})
    if "CHECKS" in sections and not report.checks:
        report.problems.append("CHECKS: section has no parseable '- name (command): STATUS' lines")

    tamper = sections.get("TAMPER SIGNALS", "")
    report.tamper_signals = [
        line.lstrip("- ").strip() for line in tamper.splitlines()
        if line.strip() and line.lstrip("- ").strip().lower() != "none"
    ]

    failures_body = sections.get("FAILURES", "")
    blocks = list(_FAILURE_BLOCK_RE.finditer(failures_body))
    for i, m in enumerate(blocks):
        end = blocks[i + 1].start() if i + 1 < len(blocks) else len(failures_body)
        report.failures[m.group(1).strip()] = failures_body[m.end():end].strip("\n")

    verdict = sections.get("VERDICT", "").strip().split()[0] if sections.get("VERDICT", "").strip() else ""
    report.verdict = verdict
    if "VERDICT" in sections and verdict not in VERDICTS:
        report.problems.append(f"VERDICT must be GREEN or RED, got: {verdict!r}")

    failing = [c["name"] for c in report.checks if c["status"] == "FAIL"]
    if verdict == "GREEN" and failing:
        report.problems.append(f"VERDICT GREEN contradicts FAIL checks: {', '.join(failing)}")
    for name in failing:
        if name not in report.failures:
            report.problems.append(f"FAIL check {name!r} has no FAILURES block")

    return report


# ---------------------------------------------------------------------------
# Failure-signature normalization
# ---------------------------------------------------------------------------

_NOISE_PATTERNS = (
    re.compile(r"0x[0-9a-fA-F]+"),                      # heap addresses
    re.compile(r"/tmp/\S+|/var/folders/\S+"),           # tmp paths
    re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?\S*"),  # timestamps
    re.compile(r"\b\d{2}:\d{2}:\d{2}(?:\.\d+)?\b"),     # clock times
    re.compile(r"\bin \d+(?:\.\d+)?s\b"),               # durations ("in 0.32s")
    re.compile(r"\b\d+(?:\.\d+)? ?(?:ms|s|sec|seconds)\b"),  # bare durations
    re.compile(r"\bpid[= ]\d+\b", re.IGNORECASE),       # process ids
)

_TEST_ID_PATTERNS = (
    re.compile(r"FAILED\s+(\S+::\S+)"),                # pytest
    re.compile(r"^ERROR\s+(\S+::\S+)", re.MULTILINE),  # pytest collection errors
    re.compile(r"^--- FAIL: (\S+)", re.MULTILINE),     # go test
    re.compile(r"^test (\S+) \.\.\. FAILED", re.MULTILINE),  # cargo test
    re.compile(r"^\s*[✕✗×]\s+(.+?)(?:\s+\(\d+.*\))?\s*$", re.MULTILINE),  # jest/vitest
    re.compile(r"^\s*●\s+(.+?)\s*$", re.MULTILINE),    # jest suite headers
    re.compile(r"^(\S+\.tsx?)\(\d+,\d+\): error TS\d+", re.MULTILINE),  # tsc (file only)
)

_ERROR_CLASS_PATTERNS = (
    re.compile(r"\b([A-Z][A-Za-z]*(?:Error|Exception|Failure|Warning))\b"),
    re.compile(r"\berror (TS\d+)\b"),
    re.compile(r"\berror\[?(E\d{4})\]?"),
)


def normalize_error_text(text: str) -> str:
    for pattern in _NOISE_PATTERNS:
        text = pattern.sub("<X>", text)
    return text


def signature_items(report: CheckerReport) -> list:
    """Extract sorted, normalized (check, test_id, error_class) triples from failures."""
    items = set()
    for check in report.checks:
        if check["status"] != "FAIL":
            continue
        name = check["name"]
        block = normalize_error_text(report.failures.get(name, ""))
        test_ids = set()
        for pattern in _TEST_ID_PATTERNS:
            test_ids.update(m if isinstance(m, str) else m[0] for m in pattern.findall(block))
        error_classes = set()
        for pattern in _ERROR_CLASS_PATTERNS:
            error_classes.update(pattern.findall(block))
        if not test_ids and not error_classes:
            digest = hashlib.sha256(block[:400].encode()).hexdigest()[:12]
            items.add((name, "-", f"text:{digest}"))
            continue
        for test_id in sorted(test_ids) or ["-"]:
            for error_class in sorted(error_classes) or ["-"]:
                items.add((name, test_id, error_class))
    return sorted(items)


def failure_signature(report: CheckerReport) -> str:
    """Stable hash of the failure set; equal signatures across cycles = no progress."""
    return hashlib.sha256(json.dumps(signature_items(report)).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Baseline classification (fail-to-pass targets vs pass-to-pass protected)
# ---------------------------------------------------------------------------

def classify_baseline(report: CheckerReport) -> dict:
    return {
        "targets": [c["name"] for c in report.checks if c["status"] == "FAIL"],
        "protected": [c["name"] for c in report.checks if c["status"] == "PASS"],
        "flaky": [c["name"] for c in report.checks if c["status"] == "FLAKY"],
    }


# ---------------------------------------------------------------------------
# Hook plumbing shared by all hook scripts
# ---------------------------------------------------------------------------

def debug_log(payload: dict, script: str) -> None:
    """PARROT_DEBUG=1: append raw hook payloads to plugin data for field-drift triage."""
    if os.environ.get("PARROT_DEBUG") != "1":
        return
    try:
        log_dir = plugin_data_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "debug.jsonl", "a") as fh:
            fh.write(json.dumps({"script": script, "payload": payload}) + "\n")
    except OSError:
        pass  # debug logging must never break enforcement


def plugin_data_dir():
    from pathlib import Path
    env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "plugins" / "data" / "parrot-parrot"
