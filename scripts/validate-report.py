#!/usr/bin/env python3
"""parrot report validator: SubagentStop hook on parrot verdict agents.

Each verdict-bearing agent's report is "parsed downstream" — this hook makes
those contracts machine-enforced: an agent whose final message does not parse
is sent back (at most twice) with the exact contract text. Fail-open by
design: if the payload shape drifts and no final message can be located, the
stop is allowed — a validator that can't see the report must not deadlock
the loop.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parrot_common import REPORT_CONTRACT, debug_log, parse_checker_report, plugin_data_dir  # noqa: E402

MAX_RETRIES = 2

# Reviewer contracts: required patterns in the final message, plus the text
# quoted back on a violation.
REVIEWER_CONTRACTS = {
    "parrot:spec-reviewer": {
        "patterns": [r"^MISSING:", r"^UNREQUESTED:", r"^SPEC VERDICT: (PASS|FAIL)\s*$"],
        "contract": "MISSING:\n- none | findings\n\nUNREQUESTED:\n- none | findings\n\nSPEC VERDICT: PASS | FAIL",
    },
    "parrot:code-reviewer": {
        "patterns": [r"^FINDINGS:", r"^REVIEW VERDICT: (PASS|FAIL)\s*$"],
        "contract": "FINDINGS:\n- none | one line each\n\nREVIEW VERDICT: PASS | FAIL",
    },
    "parrot:security-auditor": {
        "patterns": [r"^FINDINGS:", r"^SECURITY VERDICT: (PASS|FAIL)\s*$"],
        "contract": "FINDINGS:\n- none | severity — file:line — narrative — precondition\n\nSECURITY VERDICT: PASS | FAIL",
    },
}


def validate(agent: str, final: str):
    """Returns (valid: bool, problems: str, contract: str)."""
    if agent == "parrot:checker":
        report = parse_checker_report(final)
        return report.valid, "; ".join(report.problems), REPORT_CONTRACT
    spec = REVIEWER_CONTRACTS[agent]
    missing = [p for p in spec["patterns"]
               if not re.search(p, final, re.MULTILINE)]
    return not missing, f"missing required lines: {', '.join(missing)}", spec["contract"]


def find_final_message(payload: dict) -> str:
    for key in ("last_assistant_message", "final_message", "last_message", "agent_message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in ("agent_transcript_path", "transcript_path"):
        path = payload.get(key)
        if not path or not Path(path).exists():
            continue
        last_text = ""
        try:
            for line in Path(path).read_text().splitlines():
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = entry.get("message") or {}
                if (entry.get("type") == "assistant" or message.get("role") == "assistant"):
                    content = message.get("content")
                    if isinstance(content, list):
                        text = "".join(
                            block.get("text", "") for block in content
                            if isinstance(block, dict) and block.get("type") == "text"
                        )
                    else:
                        text = content if isinstance(content, str) else ""
                    if text.strip():
                        last_text = text
        except OSError:
            continue
        if last_text:
            return last_text
    return ""


def retry_file(payload: dict) -> Path:
    session = "".join(ch for ch in payload.get("session_id", "default") if ch.isalnum() or ch in "-_") or "default"
    agent = "".join(ch for ch in str(payload.get("agent_id", "any")) if ch.isalnum())[:12] or "any"
    return plugin_data_dir() / "retries" / f"{session}-{agent}.json"


def main() -> int:
    payload = json.load(sys.stdin)
    debug_log(payload, "validate-report")
    agent = payload.get("agent_type", "")
    if agent != "parrot:checker" and agent not in REVIEWER_CONTRACTS:
        return 0

    final = find_final_message(payload)
    if not final:
        return 0  # fail-open: cannot see the report, must not deadlock

    valid, problems, contract = validate(agent, final)
    marker = retry_file(payload)
    if valid:
        if marker.exists():
            marker.unlink()
        return 0

    retries = 0
    if marker.exists():
        try:
            retries = json.loads(marker.read_text()).get("retries", 0)
        except (json.JSONDecodeError, OSError):
            retries = 0
    if retries >= MAX_RETRIES:
        marker.unlink()
        return 0  # give up; orchestrator handles the malformed report

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"retries": retries + 1}))
    print(json.dumps({
        "decision": "block",
        "reason": (
            f"parrot: your report failed the machine contract ({problems}). "
            "Re-emit your ENTIRE final message in exactly this format:\n\n"
            + contract
        ),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
