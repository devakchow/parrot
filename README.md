# parrot

A Claude Code plugin that runs a builder/checker agent loop: one agent writes code, a separate agent verifies it (tests, type checks, lint), and an orchestrator command cycles them until everything is green — with hard stop rules so the loop can't burn tokens or weaken tests to fake a pass.

This is the [evaluator-optimizer pattern](https://www.anthropic.com/engineering/building-effective-agents): generation and evaluation in separate contexts, because an agent checking its own code misses its own blind spots.

## What's inside

| Piece | Role |
|---|---|
| `agents/builder.md` | Writes and fixes code only. Never runs the suite. Forbidden from editing tests, skipping tests, adding suppressions, or touching check configs. |
| `agents/checker.md` | Runs tests + typecheck + lint only. Never edits. Reports exact failures in a parseable format, plus a tamper scan of changed test/config files. |
| `skills/loop/SKILL.md` | The orchestrator: `/parrot:loop <task>`. Baselines first, then cycles builder → checker. User-invoked only (`disable-model-invocation`). |
| `hooks/hooks.json` + `scripts/guard-builder.py` | Deterministic guard: a PreToolUse hook that blocks the builder agent from editing test files or check configs, regardless of what the model decides. |

## Stop rules

1. **Max 5 cycles.** Not green after 5 builder dispatches → halt, hand to human.
2. **Regression halt.** Any check that passed in an earlier run (including the pre-work baseline) fails later → immediate halt. Something is being broken to fix something else.
3. **Tamper halt.** Test files or test/lint/type configs modified when the task didn't ask for it → immediate halt. That's the loop trying to weaken checks instead of fixing code. Enforced twice: the guard hook blocks the builder's edit at the tool layer, and the checker's tamper scan catches anything that slips past (e.g. edits via Bash).

## Install

From GitHub:

```
/plugin marketplace add devakchow/parrot
/plugin install parrot@parrot
```

From a local clone:

```
/plugin marketplace add /path/to/parrot
/plugin install parrot@parrot
```

Auto-install on other machines (add to `~/.claude/settings.json`):

```json
{
  "extraKnownMarketplaces": {
    "parrot": {
      "source": { "source": "github", "repo": "devakchow/parrot" }
    }
  },
  "enabledPlugins": {
    "parrot@parrot": true
  }
}
```

## Use

```
/parrot:loop add input validation to the signup endpoint; pytest and mypy must stay green
```

Naming the check commands in the task helps the checker skip discovery. Without them it discovers checks from CLAUDE.md, package.json scripts, Makefile, pyproject.toml, or stack defaults.

## Flow

```
baseline check ──► builder ──► checker ──► green? ──► done
                     ▲                       │
                     └── exact failures ◄────┘
                         (max 5 cycles; halt on regression or tamper)
```
