#!/usr/bin/env python3
"""parrot report validator: SubagentStop hook on parrot:checker.

The checker's report is "parsed downstream" — this hook makes that contract
machine-enforced: a checker whose final message does not parse is sent back
(at most twice) with the exact contract text. Fail-open by design: if the
payload shape drifts and no final message can be located, the stop is
allowed — a validator that can't see the report must not deadlock the loop.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parrot_common import REPORT_CONTRACT, debug_log, parse_checker_report, plugin_data_dir  # noqa: E402

MAX_RETRIES = 2


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
    if payload.get("agent_type") != "parrot:checker":
        return 0

    final = find_final_message(payload)
    if not final:
        return 0  # fail-open: cannot see the report, must not deadlock

    report = parse_checker_report(final)
    marker = retry_file(payload)
    if report.valid:
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
        return 0  # give up; orchestrator sees INVALID-REPORT from record-verdict

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"retries": retries + 1}))
    problems = "; ".join(report.problems)
    print(json.dumps({
        "decision": "block",
        "reason": (
            f"parrot: your report failed the machine contract ({problems}). "
            "Re-emit your ENTIRE final message in exactly this format:\n\n"
            + REPORT_CONTRACT
        ),
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
