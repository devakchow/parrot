#!/usr/bin/env python3
"""parrot state CLI: the only writer of loop state and run artifacts.

The loop orchestrator has no Edit/Write tools; every state mutation flows
through this script so it is scoped (refuses paths outside .parrot/ and the
plugin data dir), auditable, and unit-testable. Stdlib only.

Verbs (all print a single JSON object on stdout):
  init-project      create .parrot/ + .gitignore
  init-run          create run dir + session state; prunes stale session files
  record-baseline   stdin: checker report -> baseline.json (targets/protected)
  snapshot-integrity  hash all guarded files -> integrity.json
  verify-integrity  recompute hashes, diff vs snapshot
  record-verdict    stdin: checker report -> verdict-<n>.md + status line
  append-ledger     stdin: markdown -> ledger.md under a cycle header
  write-escalation  stdin: markdown -> escalation.md
  get-state         print session state
  end-run           finalize state with a terminal status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parrot_common import (  # noqa: E402
    classify_baseline,
    failure_signature,
    guarded_kind,
    parse_checker_report,
    plugin_data_dir,
    plugin_option,
)

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"
STALE_RUN_SECONDS = 7 * 24 * 3600
TERMINAL_STATUSES = (
    "GREEN", "REGRESSION-HALT", "TAMPER-HALT", "MAX-CYCLES-HALT",
    "STALLED-HALT", "INFEASIBLE-HALT",
)


def emit(obj: dict) -> None:
    print(json.dumps(obj, indent=2))


def fail(message: str) -> "NoReturn":  # noqa: F821
    print(json.dumps({"error": message}), file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# State + path helpers
# ---------------------------------------------------------------------------

def state_path(session: str) -> Path:
    safe = "".join(ch for ch in session if ch.isalnum() or ch in "-_") or "default"
    return plugin_data_dir() / "runs" / f"{safe}.json"


def load_state(session: str) -> dict:
    path = state_path(session)
    if not path.exists():
        fail(f"no run state for session {session!r}; run init-run first")
    return json.loads(path.read_text())


def save_state(session: str, state: dict) -> None:
    path = state_path(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def run_dir(state: dict) -> Path:
    path = Path(state["run_dir"])
    if ".parrot" not in path.parts:
        fail(f"run_dir escaped .parrot/: {path}")
    return path


def prune_stale(now: float) -> None:
    runs = plugin_data_dir() / "runs"
    if not runs.is_dir():
        return
    for path in runs.glob("*.json"):
        try:
            if now - path.stat().st_mtime > STALE_RUN_SECONDS:
                path.unlink()
        except OSError:
            pass  # a vanished stale file is the desired end state


# ---------------------------------------------------------------------------
# Guarded-file integrity
# ---------------------------------------------------------------------------

def git_lines(project: Path, *args: str) -> list:
    result = subprocess.run(
        ["git", "-C", str(project), *args],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        fail(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def guarded_files(project: Path) -> list:
    tracked = git_lines(project, "ls-files")
    untracked = git_lines(project, "ls-files", "--others", "--exclude-standard")
    return sorted(p for p in {*tracked, *untracked} if guarded_kind(p))


def hash_files(project: Path, paths: list) -> dict:
    hashes = {}
    for rel in paths:
        full = project / rel
        try:
            hashes[rel] = hashlib.sha256(full.read_bytes()).hexdigest()
        except OSError:
            hashes[rel] = "<unreadable>"
    return hashes


# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------

_RUBRIC_HEADER = "## "


def parse_rubrics(md_text: str) -> dict:
    """Split a profile .md into per-role rubric sections keyed by '## <role>'."""
    rubrics: dict = {}
    role, lines = None, []
    for line in md_text.splitlines():
        if line.startswith(_RUBRIC_HEADER):
            if role:
                rubrics[role] = "\n".join(lines).strip()
            role, lines = line[len(_RUBRIC_HEADER):].strip(), []
        elif role:
            lines.append(line)
    if role:
        rubrics[role] = "\n".join(lines).strip()
    return rubrics


def load_profile(name: str, overlays: list) -> dict:
    base_json = PROFILES_DIR / f"{name}.json"
    if not base_json.exists():
        available = sorted(p.stem for p in PROFILES_DIR.glob("*.json"))
        fail(f"unknown profile {name!r}; available: {', '.join(available)}")
    config = json.loads(base_json.read_text())
    rubrics = parse_rubrics((PROFILES_DIR / f"{name}.md").read_text()) \
        if (PROFILES_DIR / f"{name}.md").exists() else {}
    resolved = {
        "name": config["name"],
        "displayName": config.get("displayName", name),
        "tagline": config.get("tagline", ""),
        "philosophy": config.get("philosophy", ""),
        "loop": config.get("loop", {}),
        "roles": config.get("roles", {}),
        "gates": list(config.get("gates", [])),
        "rubrics": rubrics,
        "overlays": [],
    }
    for overlay_name in overlays:
        overlay_json = PROFILES_DIR / "overlays" / f"{overlay_name}.json"
        if not overlay_json.exists():
            fail(f"unknown overlay {overlay_name!r}")
        overlay = json.loads(overlay_json.read_text())
        resolved["overlays"].append(overlay_name)
        resolved["gates"].extend(overlay.get("gates", []))
        for role, mode in overlay.get("roles", {}).items():
            resolved["roles"][role] = mode
        overlay_md = PROFILES_DIR / "overlays" / f"{overlay_name}.md"
        if overlay_md.exists():
            for role, text in parse_rubrics(overlay_md.read_text()).items():
                existing = resolved["rubrics"].get(role, "")
                addition = f"[overlay: {overlay_name}]\n{text}"
                resolved["rubrics"][role] = f"{existing}\n\n{addition}".strip()
    return resolved


def resolve_profile_choice(project: Path, cli_profile, cli_overlays) -> tuple:
    """Resolution order: CLI flag > userConfig option > .parrot/profile.json > google."""
    if cli_profile:
        return cli_profile, list(cli_overlays or [])
    option = plugin_option("profile", "")
    if option:
        return option, list(cli_overlays or [])
    choice_file = project / ".parrot" / "profile.json"
    if choice_file.exists():
        try:
            choice = json.loads(choice_file.read_text())
            return choice.get("profile", "google"), choice.get("overlays", [])
        except (json.JSONDecodeError, OSError):
            pass  # corrupt choice file falls back to the default profile
    return "google", []


# ---------------------------------------------------------------------------
# Verbs
# ---------------------------------------------------------------------------

def cmd_init_project(args) -> None:
    project = Path(args.project).resolve()
    parrot = project / ".parrot"
    parrot.mkdir(exist_ok=True)
    gitignore = parrot / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("runs/\n")
    emit({"ok": True, "dir": str(parrot)})


def cmd_init_run(args) -> None:
    project = Path(args.project).resolve()
    (project / ".parrot").mkdir(exist_ok=True)
    gitignore = project / ".parrot" / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("runs/\n")

    now = time.time()
    prune_stale(now)
    session8 = ("".join(ch for ch in args.session if ch.isalnum()) or "default")[:8]
    run_id = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now)) + f"-{session8}"
    rdir = project / ".parrot" / "runs" / run_id
    rdir.mkdir(parents=True)

    task = sys.stdin.read().strip() if not sys.stdin.isatty() else ""
    if task:
        (rdir / "task.md").write_text(task + "\n")

    profile_name, overlays = resolve_profile_choice(project, args.profile, args.overlay)
    profile = load_profile(profile_name, overlays)
    max_cycles = args.max_cycles or profile.get("loop", {}).get("max_cycles") \
        or plugin_option("max_cycles", 5)

    state = {
        "run_id": run_id,
        "project": str(project),
        "run_dir": str(rdir),
        "session": args.session,
        "cycle": 0,
        "verdicts": 0,
        "max_cycles": int(max_cycles),
        "allow_guarded": args.allow_guarded,
        "baseline": None,
        "signatures": [],
        "report_retry": 0,
        "status": "RUNNING",
        "started_at": now,
        "profile": profile,
    }
    save_state(args.session, state)
    active_roles = sorted(r for r, mode in profile["roles"].items() if mode == "on")
    emit({"run_id": run_id, "run_dir": str(rdir), "max_cycles": int(max_cycles),
          "allow_guarded": args.allow_guarded,
          "profile": profile_name, "overlays": profile["overlays"],
          "tagline": profile["tagline"], "active_roles": active_roles,
          "conditional_roles": sorted(r for r, mode in profile["roles"].items()
                                      if mode == "auto-large"),
          "gates": [{"id": g["id"], "blocking": g.get("blocking", False),
                     "description": g["description"]} for g in profile["gates"]]})


def cmd_record_baseline(args) -> None:
    state = load_state(args.session)
    report = parse_checker_report(sys.stdin.read())
    if not report.valid:
        emit({"status": "INVALID-REPORT", "problems": report.problems})
        sys.exit(0)
    baseline = classify_baseline(report)
    baseline["inventory"] = report.inventory
    baseline["changed_files"] = report.changed_files
    baseline["checks"] = report.checks
    state["baseline"] = baseline
    save_state(args.session, state)
    (run_dir(state) / "baseline.json").write_text(json.dumps(baseline, indent=2))
    emit({"status": "BASELINE-RECORDED", "targets": baseline["targets"],
          "protected": baseline["protected"], "flaky": baseline["flaky"],
          "pre_existing_dirty": baseline["changed_files"]})


def cmd_snapshot_integrity(args) -> None:
    state = load_state(args.session)
    project = Path(state["project"])
    hashes = hash_files(project, guarded_files(project))
    (run_dir(state) / "integrity.json").write_text(json.dumps(hashes, indent=2))
    emit({"status": "SNAPSHOT-RECORDED", "guarded_files": len(hashes)})


def cmd_verify_integrity(args) -> None:
    state = load_state(args.session)
    project = Path(state["project"])
    snapshot_file = run_dir(state) / "integrity.json"
    if not snapshot_file.exists():
        fail("no integrity snapshot; run snapshot-integrity at baseline")
    before = json.loads(snapshot_file.read_text())
    after = hash_files(project, guarded_files(project))
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(p for p in set(before) & set(after) if before[p] != after[p])
    clean = not (added or removed or modified)
    if clean:
        status = "PASS"
    elif state.get("allow_guarded"):
        status = "ADVISORY"  # task explicitly put tests/configs in scope
    else:
        status = "FAIL"
    emit({"status": status, "added": added, "removed": removed, "modified": modified})


def cmd_record_verdict(args) -> None:
    state = load_state(args.session)
    if state.get("baseline") is None:
        fail("no baseline recorded; run record-baseline first")
    text = sys.stdin.read()
    report = parse_checker_report(text)
    state["verdicts"] += 1
    n = state["verdicts"]
    (run_dir(state) / f"verdict-{n}.md").write_text(text)

    if not report.valid:
        save_state(args.session, state)
        emit({"status": "INVALID-REPORT", "verdict_n": n, "problems": report.problems})
        return

    protected = set(state["baseline"]["protected"])
    regressions = sorted(
        c["name"] for c in report.checks
        if c["name"] in protected and c["status"] == "FAIL"
    )
    flaky = sorted(c["name"] for c in report.checks if c["status"] == "FLAKY")
    signature = failure_signature(report)
    previous = state["signatures"][-1] if state["signatures"] else None
    state["signatures"].append(signature)
    save_state(args.session, state)

    if report.tamper_signals:
        status = "TAMPER"
    elif regressions:
        status = "REGRESSION"
    elif report.verdict == "GREEN":
        status = "GREEN-CANDIDATE"
    elif previous is not None and signature == previous:
        status = "STALLED"
    else:
        status = "PROGRESS"
    emit({
        "status": status,
        "verdict_n": n,
        "verdict": report.verdict,
        "regressions": regressions,
        "tamper_signals": report.tamper_signals,
        "flaky": flaky,
        "signature": signature[:12],
        "inventory": report.inventory,
        "baseline_inventory": state["baseline"].get("inventory", {}),
    })


def cmd_append_ledger(args) -> None:
    state = load_state(args.session)
    entry = sys.stdin.read().strip()
    if not entry:
        fail("empty ledger entry")
    ledger = run_dir(state) / "ledger.md"
    with ledger.open("a") as fh:
        fh.write(f"\n## Cycle {args.cycle}\n\n{entry}\n")
    emit({"ok": True, "ledger": str(ledger)})


def cmd_write_escalation(args) -> None:
    state = load_state(args.session)
    body = sys.stdin.read().strip()
    if not body:
        fail("empty escalation body")
    path = run_dir(state) / "escalation.md"
    path.write_text(body + "\n")
    emit({"ok": True, "escalation": str(path)})


def cmd_set_profile(args) -> None:
    project = Path(args.project).resolve()
    overlays = list(args.overlay or [])
    load_profile(args.name, overlays)  # validates both exist
    parrot = project / ".parrot"
    parrot.mkdir(exist_ok=True)
    choice = {
        "profile": args.name,
        "overlays": overlays,
        "chosen_by": args.chosen_by,
        "evidence": json.loads(args.evidence) if args.evidence else [],
        "version": 1,
    }
    (parrot / "profile.json").write_text(json.dumps(choice, indent=2) + "\n")
    emit({"ok": True, "profile": args.name, "overlays": overlays,
          "file": str(parrot / "profile.json")})


def cmd_get_state(args) -> None:
    emit(load_state(args.session))


def cmd_end_run(args) -> None:
    state = load_state(args.session)
    if args.status not in TERMINAL_STATUSES:
        fail(f"status must be one of {TERMINAL_STATUSES}")
    state["status"] = args.status
    state["ended_at"] = time.time()
    save_state(args.session, state)
    (run_dir(state) / "status").write_text(args.status + "\n")
    emit({"ok": True, "run_id": state["run_id"], "status": args.status})


def main() -> None:
    parser = argparse.ArgumentParser(prog="parrot_state")
    sub = parser.add_subparsers(dest="verb", required=True)

    def add(name, func, **flags):
        p = sub.add_parser(name)
        p.set_defaults(func=func)
        for flag, kwargs in flags.items():
            p.add_argument(flag, **kwargs)
        return p

    add("init-project", cmd_init_project, **{"--project": dict(default=".")})
    add("init-run", cmd_init_run, **{
        "--session": dict(required=True),
        "--project": dict(default="."),
        "--max-cycles": dict(type=int, default=None),
        "--allow-guarded": dict(action="store_true"),
        "--profile": dict(default=None),
        "--overlay": dict(action="append", default=None),
    })
    add("record-baseline", cmd_record_baseline, **{"--session": dict(required=True)})
    add("set-profile", cmd_set_profile, **{
        "--name": dict(required=True),
        "--project": dict(default="."),
        "--overlay": dict(action="append", default=None),
        "--chosen-by": dict(default="user"),
        "--evidence": dict(default=None),
    })
    add("snapshot-integrity", cmd_snapshot_integrity, **{"--session": dict(required=True)})
    add("verify-integrity", cmd_verify_integrity, **{"--session": dict(required=True)})
    add("record-verdict", cmd_record_verdict, **{"--session": dict(required=True)})
    add("append-ledger", cmd_append_ledger, **{
        "--session": dict(required=True),
        "--cycle": dict(type=int, required=True),
    })
    add("write-escalation", cmd_write_escalation, **{"--session": dict(required=True)})
    add("get-state", cmd_get_state, **{"--session": dict(required=True)})
    add("end-run", cmd_end_run, **{
        "--session": dict(required=True),
        "--status": dict(required=True),
    })

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
