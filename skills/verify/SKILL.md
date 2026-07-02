---
name: verify
description: One-shot verification - dispatch the parrot checker to discover and run the project's tests, typecheck, and lint, then relay the exact pass/fail report. The reusable primitive for other plugins and workflows; no loop, no state.
argument-hint: [check commands to run, if known]
---

Dispatch a single verification pass and relay the results. This is the parrot checker outside the loop: read-only (hook-enforced), machine-parseable report, no state, no cycles.

1. Spawn `parrot:checker` via the Agent tool. Prompt: any check commands given in <args>$ARGUMENTS</args>, plus the current `git status --porcelain` output as the pre-existing dirty list. If `.parrot/checks.json` exists, mention it (the checker reads it to skip discovery).
2. Relay the checker's report to the caller verbatim — the CHECKS, TAMPER SIGNALS, and VERDICT sections are the contract; do not summarize away the failure details.
3. One dispatch only. If the report is malformed after the validator's retries, say so and show what came back. Never edit files or run the checks yourself in the main thread.
