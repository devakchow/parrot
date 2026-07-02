#!/usr/bin/env python3
"""parrot bash guard: PreToolUse hook on Bash.

Closes the shell bypass of the Edit/Write guard: the builder cannot use
sed -i / tee / redirection / rm to alter test files or check configs, and
the read-only agents (checker, reviewers) cannot write at all. Heuristic
by design — the pre-GREEN integrity hash is the backstop for anything
this misses. No-ops for non-parrot agents and the main thread.
"""
import json
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parrot_common import debug_log, guarded_kind  # noqa: E402

READ_ONLY_AGENTS = {
    "parrot:checker",
    "parrot:spec-reviewer",
    "parrot:code-reviewer",
    "parrot:security-auditor",
}
# Agents that may write, but only inside .parrot/ artifacts.
FENCED_WRITERS = {"parrot:planner", "parrot:memory-codifier"}

# Commands that write to a path argument (builder: denied against guarded
# paths; read-only agents: denied outright).
WRITE_COMMANDS = {
    "tee", "mv", "cp", "rm", "truncate", "install", "patch", "chmod",
    "ln", "touch", "mkdir", "rsync", "dd",
}
GIT_WRITE_SUBCOMMANDS = {
    "apply", "checkout", "restore", "reset", "clean", "stash",
    "commit", "add", "rm", "mv",
}

_REDIRECT_RE = re.compile(r"(?:^|[^><&\d])(?:\d?>{1,2}|&>)\s*([^\s;|&<>]+)")
_ALLOWED_REDIRECT_TARGETS = re.compile(r"^(/dev/null|/dev/std(out|err)|&\d)$")


def tokens_of(command: str) -> list:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def redirect_targets(command: str) -> list:
    return [t for t in _REDIRECT_RE.findall(command)
            if not _ALLOWED_REDIRECT_TARGETS.match(t)]


def write_targets(command: str) -> list:
    """Paths a command shape could write to (redirects + args of write commands)."""
    targets = list(redirect_targets(command))
    for segment in re.split(r"[;|&]+", command):
        words = tokens_of(segment)
        if not words:
            continue
        head = Path(words[0]).name
        if head in ("sed", "perl") and any(w == "-i" or w.startswith("-i") for w in words[1:]):
            targets.extend(w for w in words[1:] if not w.startswith("-"))
        elif head == "git" and len(words) > 1 and words[1] in GIT_WRITE_SUBCOMMANDS:
            targets.extend(w for w in words[2:] if not w.startswith("-"))
        elif head == "dd":
            targets.extend(w[3:] for w in words[1:] if w.startswith("of="))
        elif head in WRITE_COMMANDS:
            targets.extend(w for w in words[1:] if not w.startswith("-"))
    return targets


def has_write_shape(command: str) -> bool:
    if redirect_targets(command):
        return True
    for segment in re.split(r"[;|&]+", command):
        words = tokens_of(segment)
        if not words:
            continue
        head = Path(words[0]).name
        if head in WRITE_COMMANDS:
            return True
        if head in ("sed", "perl") and any(w == "-i" or w.startswith("-i") for w in words[1:]):
            return True
        if head == "git" and len(words) > 1 and words[1] in GIT_WRITE_SUBCOMMANDS:
            return True
    return False


def deny(message: str) -> int:
    print(f"parrot guard: {message}", file=sys.stderr)
    return 2


def check_builder(command: str) -> int:
    for target in write_targets(command):
        if ".parrot" in Path(target).parts:
            return deny(
                "builder may not write into .parrot/ — loop artifacts are "
                "written only by the orchestrator's state CLI."
            )
        kind = guarded_kind(target)
        if kind:
            return deny(
                f"builder may not modify {kind} ({target}) — not even via the "
                "shell. Fix the implementation instead, or report INFEASIBLE."
            )
    return 0


def check_read_only(agent: str, command: str) -> int:
    if has_write_shape(command):
        return deny(
            f"{agent.split(':')[1]} is read-only: it runs checks and reports "
            "facts, it never writes. Capture output via pipes or variables "
            "instead of redirecting to files."
        )
    return 0


def check_fenced(agent: str, command: str) -> int:
    if not has_write_shape(command):
        return 0
    targets = write_targets(command)
    if targets and all(".parrot" in Path(t).parts for t in targets):
        return 0
    return deny(
        f"{agent.split(':')[1]} may write only inside .parrot/ "
        f"(command: {command[:120]}). Propose other changes in your final "
        "message instead."
    )


def main() -> int:
    payload = json.load(sys.stdin)
    debug_log(payload, "guard-bash")
    agent = payload.get("agent_type", "")
    command = (payload.get("tool_input") or {}).get("command", "") or ""
    if agent == "parrot:builder":
        return check_builder(command)
    if agent in READ_ONLY_AGENTS:
        return check_read_only(agent, command)
    if agent in FENCED_WRITERS:
        return check_fenced(agent, command)
    return 0


if __name__ == "__main__":
    sys.exit(main())
