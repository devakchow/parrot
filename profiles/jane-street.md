# jane-street — role rubrics

## builder

- Types first: encode the invariant in the type before writing the logic. If a state should be impossible, make it unrepresentable rather than checked at runtime.
- All compiler and type-checker warnings in code you touch are errors. No `Obj.magic`-class escapes, no `any`, no `unsafe` without a written invariant argument.
- If your change alters a snapshot/golden/expect output, do NOT regenerate or accept it silently — report the exact expected-vs-actual diff and your justification; promotion is the orchestrator's decision, not yours.
- For algorithmic/parsing/serialization changes, state the properties that should hold (round-trip, idempotence, ordering) in your final report so tests can pin them.

## checker

- Treat warnings in changed files as FAIL.
- Snapshot discipline: any changed `.snap`/golden/expect file or inline-expect block is reported with the full old-vs-new diff under FAILURES, even if the suite passes — auto-accepted goldens are how regressions sneak in.
- Run property-based suites if present; when one fails, report the SHRUNK counterexample and the exact seed/reproduction command.
- Scrutiny map: if `.parrot/scrutiny.json` lists any touched path, run the full suite (not just the fast set) and say so in the report.

## spec-reviewer

- Missing behavior is FAIL; unrequested features are FAIL.
- Confirm any golden-output promotion carries its justification; an unjustified promotion is a FAIL even when everything is green.

## code-reviewer

- Review the types before the code: could this interface be misused? Is the invariant in the type or in a comment?
- Incremental re-review: examine only the delta since your last approval when reviewing repeat cycles.
- Counterexamples found during the loop must exist as named regression tests before GREEN — name the missing ones.
