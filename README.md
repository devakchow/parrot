# parrot

**Hire a top-tier engineering team with deterministic guardrails.**

Parrot is a Claude Code plugin that staffs a full engineering team around your task — builder, checker, planner, spec reviewer, code reviewer, security auditor — disciplined like the company you choose: Google, Meta, Palantir, Jane Street, NASA/JPL, or Stripe. The loop cycles until every check is green, and its stop rules are enforced by hooks, not by prompts: the builder physically cannot weaken a test, the checker physically cannot edit code, and the loop physically cannot overspend its cycle budget.

This is the [evaluator-optimizer pattern](https://www.anthropic.com/engineering/building-effective-agents) — generation and evaluation in separate contexts, because an agent checking its own code misses its own blind spots — hardened into an enforcement layer.

## Why parrot over a prompt-level loop

Every "keep going until done" loop faces the same failure: under pressure, coding agents weaken checks instead of fixing code — deleting tests, hardcoding expected values, adding `conftest.py` hooks, exiting 0 mid-harness ([documented by Anthropic](https://www.anthropic.com/research/emergent-misalignment-reward-hacking)). Most tools counter this with instructions ("don't cheat") or with an LLM judge that only reads the transcript. Parrot counters it in layers that hold even when the model drifts:

1. **Tool-layer guards (deterministic).** PreToolUse hooks block the builder from editing test files, harness hooks, or check configs — via Edit/Write *and* via shell (`sed -i`, `tee`, redirection, `rm`). Reviewer agents are read-only at the same layer.
2. **Spawn gate (deterministic).** The cycle counter lives in a hook, not in the orchestrator's memory. Builder dispatch #6 is denied, period.
3. **Integrity hashing (deterministic).** Every test file and check config is hashed at baseline and re-verified before GREEN — whatever slips past the guards gets caught here.
4. **Tamper scan + report contract (validated).** The checker reports tamper signals (new `conftest.py`/`sitecustomize.py`, `sys.exit(0)`, `__eq__` overrides, hardcoded test literals, shrinking test inventory) in a machine-parsed format that a SubagentStop hook rejects if malformed.
5. **Honest escape hatch.** The builder has a sanctioned `INFEASIBLE:` channel, so honesty is cheaper than cheating.

## The loop

```
/parrot:loop add input validation to the signup endpoint; pytest and mypy must stay green
```

- **Baseline** — the checker runs first. Checks are classified: already-failing ones are *targets*, passing ones are *protected*. Pre-existing failures are not the builder's fault and pre-existing dirt is not tamper.
- **Cycle** (max 5 builder dispatches, hook-enforced) — a fresh builder each cycle gets the task, a distilled attempt ledger (what changed, what failed, hypotheses ruled out — not a stale transcript), and the checker's exact failures. Then the checker re-verifies everything.
- **Evidence-based stop rules** — a *protected* check failing deterministically (flakes are rerun in isolation first and quarantined, never "fixed") halts the run. An identical failure signature two cycles running forces a strategy switch; at cycle 4+ it halts. Tamper halts immediately.
- **Green gate** — integrity hashes verified, profile gates walked, then the review chain: spec reviewer (missing features AND unrequested features both fail), code reviewer (profile rubric, anti-noise mandate), security auditor (when the SDL overlay is stacked).
- **Memory** — a codifier distills durable learnings (check commands, repo quirks, flaky tests) into `.parrot/` and *proposes* CLAUDE.md additions; nothing edits CLAUDE.md automatically.
- **Every halt writes an escalation**: attempts, blockers, ruled-out hypotheses, suggested alternatives, confidence — a handoff, not a dead stop.

## Profiles — hire the team

```
/parrot:hire
```

Scans your codebase (file names and manifests only; nothing executed, nothing installed), recommends a profile with evidence, and records the choice in committable `.parrot/profile.json`:

| Profile | Philosophy | Signature gates |
|---|---|---|
| **google** *(default)* | Code health over perfection | Beyoncé rule (behavior change without a test blocks), small CLs, flake quarantine, "improves code health" termination bar |
| **meta** | Move fast with stable infra | Diff stacking, new-findings-only static analysis, test-assurance filters, regression mini-postmortems |
| **palantir** | Encode taste in tooling; humans review only logic | Suppression tax (justify or fail), format-first, strictness ratchets, exact deps |
| **jane-street** | Make illegal states unrepresentable | Warnings as errors, snapshot promotion requires justification, property tests with pinned counterexamples, per-file scrutiny map |
| **nasa-jpl** | If a machine can't check it, it's a suggestion | Zero warnings, SCRUB disposition (every finding answered in writing), bounded everything, no merge with open findings |
| **stripe** | The API is forever | Public-surface diff triggers API review, backward-compat gate, type-coverage ratchet, docs travel with the API |
| **+ microsoft-sdl** *(overlay)* | Security is a phase-gate | Stacks on any base when auth/PII surface is detected: threat-model notes, blocking SAST, secrets scan every cycle |

A profile is data, not prose: JSON drives the machine side (cycle budget, staffed roles, blocking gates) and a rubric file reaches each agent through a SubagentStart hook. Profile names are evocative shorthand for public engineering-practice research — no affiliation with or endorsement by these companies.

## Composability

Parrot works alone and plays well with others:

- **`parrot:verify`** — model-invocable one-shot checker (no loop). Other plugins, skills, and workflows can call it as a cheap verification primitive.
- **`parrot:review`** — model-invocable one-shot profile-rubric review of the current diff.
- **`.parrot/` is a public contract** other tooling can read:

```
.parrot/
  profile.json      # {profile, overlays[], chosen_by, evidence[], version}   (committed)
  checks.json       # {checks: [{name, command, stage}], discovered_at}       (committed)
  learnings.md      # durable repo knowledge, one dated line per learning     (committed)
  runs/<run-id>/    # task.md, plan.md, baseline.json, integrity.json,        (gitignored)
                    # ledger.md, verdict-<n>.md, escalation.md, candidates/
```

- **Hooks are scoped**: every guard keys on `parrot:*` agent types and no-ops for the main thread and other plugins' agents.

## Skills

| Skill | Invocation | What it does |
|---|---|---|
| `/parrot:loop <task>` | user-only | The full team loop until green or a stop rule fires |
| `/parrot:hire [profile]` | user-only | Scan, recommend, and hire the engineering profile |
| `parrot:verify [commands]` | model-invocable | One-shot check run with the machine-parsed report |
| `parrot:review [focus]` | model-invocable | One-shot profile-rubric code review of the diff |

## Options (plugin settings)

| Setting | Default | Effect |
|---|---|---|
| `max_cycles` | 5 | Builder dispatches per run (the spawn gate reads this too) |
| `profile` | per-project | Force one profile everywhere, ignoring `.parrot/profile.json` |
| `oracle_enabled` | false | Ask a cross-vendor second opinion (codex/gemini CLI, if installed) at stalls and before GREEN — advisory only |
| `best_of_n` | false | Experimental: at cycle 3, sample 2 alternative fixes and let the checker pick the winner (clean-baseline repos only) |

## Install

```
/plugin marketplace add devakchow/parrot
/plugin install parrot@parrot
```

From a local clone: `/plugin marketplace add /path/to/parrot`.

## Honesty section

- The Bash guard is heuristic. A sufficiently creative bypass (e.g. base64-piped interpreters) can beat it — which is why the integrity hash at the Green gate re-checks every guarded file deterministically. Defense in depth, not a force field.
- Some profile gates are LLM-judged (assertion density, mutation-strength heuristics) and marked advisory; deterministic gates (cycle budget, integrity, read-only enforcement, report contracts) are hooks.
- Coverage/type ratchets only fire when your project already has the tooling; parrot never installs anything into your repo.

## Development

```
python3 -m pytest tests/   # 200+ tests: guards vs an adversarial corpus, state lifecycle,
                           # signature stability, profile recommendation fixtures
```
