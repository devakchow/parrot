# nasa-jpl — role rubrics

## builder

- Simple control flow: no goto, no recursion in safety-flagged paths, every loop provably bounded. If you cannot state the bound, restructure until you can.
- Check every return value, or cast to void with a comment saying why ignoring is safe.
- Assert pre/postconditions and invariants in every function you touch (side-effect-free assertions; target two per function in C-like code).
- Functions stay under ~60 lines; if your change pushes one over, split it or justify it in your final report.
- Smallest possible scope for every declaration; no post-initialization dynamic allocation in safety-flagged paths.
- SCRUB duty: your final report must respond to EVERY finding from the previous cycle's report — "fixed: <how>" or "disagree: <written justification>". Silence on a finding is a violation.

## checker

- Maximum pedantry: run compilers/type-checkers with all warnings enabled and treat any warning in changed code as FAIL.
- Run every analyzer the project has configured; report each tool's findings separately — multiple independent analyzers are the point.
- Verify the builder's SCRUB dispositions: any prior finding without an explicit fixed/disagree response in the builder's report is itself a FAIL finding.
- No severity downgrades: there is no "minor" tier; a finding is open or dispositioned.

## planner

- Before any build cycle on non-trivial tasks: enumerate failure modes of the change (what breaks if this is wrong, what is the blast radius, is it recoverable post-deploy) and the verification for each.

## spec-reviewer

- Missing behavior is FAIL; unrequested features are FAIL.
- Confirm every requirement in the task maps to a verifiable check in the report — unverifiable requirements get named as residual risk.

## code-reviewer

- Count assertions in touched functions; flag functions with fewer than two and state what invariant should be asserted.
- Flag any unbounded loop/recursion, unchecked return, or >60-line function in the diff.
- Concurrency and state machines get a written correctness argument in the review, not a skim.
