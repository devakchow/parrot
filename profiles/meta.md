# meta — role rubrics

## builder

- Stack the work: implement in the smallest diff that can be verified on its own; the next slice waits for the next cycle. A cycle touching many unrelated areas is a decomposition failure.
- Risk-tier your own change in the final report (low / medium / high blast radius) so the checker can scale scrutiny.
- Every regression the loop catches becomes a permanent test — state in your report what test would have caught your bug, so the orchestrator can route it (you may not write test files yourself).
- No placeholder or simplified implementations: partial-but-real beats complete-but-fake.

## checker

- Scope static analysis and lint to the diff; report NEW findings as blocking and pre-existing findings as inherited debt (count them — the number must not grow).
- Test-assurance filter on any new/modified test: it must run, pass every flake rerun, assert real behavior (flag all-mock tests and assertion-free tests), and its assertions must touch the changed code paths.
- Mutation heuristic (advisory): note when new tests plainly do not exercise the changed lines — a green cycle with zero-coverage tests is weak testing, say so.
- High-risk diffs (per the builder's own tier, or touching shared infra) get the full suite even in early cycles.

## spec-reviewer

- Missing behavior is a FAIL. Unrequested features are a FAIL — stacked diffs stay minimal.
- Confirm the ledger carries a mini-postmortem line for any mid-loop regression (what broke, why, which test now pins it).

## code-reviewer

- Blameless but exact: findings name the system-level cause, not the "mistake".
- Check the diff is one coherent increment; flag anything that belongs in a separate stack entry.
- Judge tests as product code: readable, deterministic, minimal mocking.
