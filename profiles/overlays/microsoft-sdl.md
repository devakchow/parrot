# microsoft-sdl — overlay rubrics (stack on any base profile)

## builder

- Touching auth, input parsing, crypto, network handling, or anything holding PII? Your final report must include a threat-model note: what asset is at stake, what the attacker controls, what entry points exist, what mitigates each.
- Never hand-roll crypto or auth primitives; use the project's established libraries. Parameterize every query; validate at trust boundaries, not deep inside.
- No secrets in code, ever — not even in tests or fixtures. Reference config/env instead.

## checker

- Scan the diff for security anti-patterns and report them under FAILURES even when tests pass: string-built SQL/shell commands, unsanitized path joins from user input, eval or unsafe deserialization on external data, disabled TLS verification, weak hashes (MD5/SHA1) for security purposes, hardcoded credentials or high-entropy literals.
- On any manifest/lockfile change: run the project's dependency audit tooling if present (npm audit, pip-audit, cargo audit) and report new known vulnerabilities as FAIL.
- Verify the builder's threat-model note exists when the diff touches security surface; its absence is a FAIL finding.

## security-auditor

- Review the full diff as an attacker: for each entry point the change adds or alters, ask what crafted input, replayed request, or race does. Report concrete attack narratives, not checklist noise.
- Verify authorization on every new/changed handler: who can call this, and is that checked server-side?
- Findings carry severity and exploit preconditions; a finding with no realistic attacker path is advisory, everything else blocks.

## code-reviewer

- Security findings are never waived for feature progress — the bug bar is absolute. If it conflicts with the deadline, the run halts and a human decides.
