---
name: hire
description: Scan the codebase, recommend an engineering profile (Google, Meta, Palantir, Jane Street, NASA/JPL, Stripe), and hire that team for this project. Optionally stacks the Microsoft-SDL security overlay.
argument-hint: [profile-name to skip the scan]
disallowed-tools: Edit, Write, NotebookEdit
---

Hire an engineering team for this project. The chosen profile drives every future `/parrot:loop` run: which roles are staffed, how strict the checker is, which gates block GREEN, and when the loop stops.

Optional argument (skips the scan when given): <requested>$ARGUMENTS</requested>

## Flow

1. **If the user named a profile in the argument**, skip to step 4 with that choice (still run step 2's scan for SDL-overlay detection).

2. **Scan**: run

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/recommend_profile.py" --project .
   ```

   The JSON gives per-profile scores, the recommended profile, whether the Microsoft-SDL security overlay should stack (auth/PII/crypto surface detected), and human-readable evidence.

3. **Ask** with AskUserQuestion (single question, header "Profile"):
   - Options: the top-3 scoring profiles plus the strongest remaining candidate if the user might reasonably want it. First option = the recommended profile, its label suffixed "(Recommended)", its description quoting the evidence one-liners from the scan.
   - Each option's description = the profile's tagline plus its signature gates (read them from `${CLAUDE_PLUGIN_ROOT}/profiles/<name>.json` if needed).
   - If the scan set `sdl_overlay: true`, add a second question (header "Security"): "Stack the Microsoft-SDL security overlay? (auth/crypto surface detected: <evidence>)" with "Yes, stack it (Recommended)" first.

4. **Record**:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/parrot_state.py" set-profile \
     --name <choice> [--overlay microsoft-sdl] \
     --chosen-by <"user"|"recommended"> --evidence '<json array of evidence strings>'
   ```

   This writes `.parrot/profile.json` — committable, so the whole team shares the same discipline.

5. **Present the team roster** (from the profile JSON): display name + tagline; the roles staffed on every run (builder, checker always; plus spec-reviewer, code-reviewer, planner-on-large-tasks, security-auditor per the profile's `roles` map); the blocking gates by id + one-line description; the cycle budget. Close with: "Run `/parrot:loop <task>` to put the team to work; `/parrot:hire <other-profile>` to switch anytime."

## Rules

- The scan never installs anything and never executes project code; it reads file names and manifests.
- Profile names are evocative shorthand for public engineering-practice research; say so if the user asks (no affiliation with the companies).
- If `.parrot/profile.json` already exists, show the current profile in the question and treat re-hiring as a switch, not an error.
