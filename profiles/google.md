# google — role rubrics

## builder

- Keep every increment small and self-contained; one logical change per cycle. If the fix wants to sprawl, do the smallest correct slice first.
- Any behavior change ships with a covering test in the same cycle — if no test exists for the behavior you changed, say so in your final report so the orchestrator can route a test task (you may not write test files yourself).
- New code is hermetic by default: no network calls, no sleeps, no wall-clock dependence in anything a test will touch.
- Prefer the boring, readable fix over the clever one. The reviewer's bar is "improves code health", not "impresses".

## checker

- Two-stage checking: run the fast hermetic set first (typecheck, lint, tests scoped to changed packages), then the full suite before any GREEN verdict.
- Test-size discipline: flag any new test that needs network, real services, or sleeps — small and hermetic is the default; medium/large needs justification.
- Flake protocol is strict: a pass-on-retry is FLAKY in the report with the retry count, never a silent PASS.
- Only actionable, high-precision findings belong in the report; noisy analyzer output that a human would dismiss is left out.

## spec-reviewer

- Judge the diff against the request and nothing else. Missing behavior is a FAIL; unrequested features are a FAIL — small CLs mean no smuggled extras.

## code-reviewer

- Approve when the change definitively improves or maintains the overall code health of the system, even if it is not perfect. Do not demand perfection — demand net improvement. This is the loop's termination bar, not an invitation to polish forever.
- Flag only what affects correctness or long-term code health. Zero style nits the formatter can fix.
- Every behavior change must have a test you can point to (Beyoncé rule). Name the missing test if not.
