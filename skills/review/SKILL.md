---
name: review
description: One-shot code review of the current diff by the parrot code-reviewer under the project's hired engineering profile (Google, Meta, Palantir, Jane Street, NASA/JPL, Stripe rubrics). Read-only; no loop.
argument-hint: [what to focus on, or a base ref like main]
---

Dispatch a single profile-rubric code review of the working tree's diff.

1. Determine the active profile: read `.parrot/profile.json` (field `profile`; default `google` when absent). Read the `## code-reviewer` section from `${CLAUDE_PLUGIN_ROOT}/profiles/<name>.md` — plus the same section from `${CLAUDE_PLUGIN_ROOT}/profiles/overlays/<overlay>.md` for each overlay listed.
2. Spawn `parrot:code-reviewer` via the Agent tool. Prompt: the rubric text from step 1, the diff scope (uncommitted changes by default; diff against the base ref if <args>$ARGUMENTS</args> names one), and any focus the caller gave.
3. Relay the FINDINGS and REVIEW VERDICT verbatim. Advisory findings stay labeled advisory — do not upgrade or drop them.
4. One dispatch, read-only (hook-enforced). Never edit files to "help" with the findings unless the user then asks for fixes.
