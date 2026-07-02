# palantir — role rubrics

## builder

- Fix, never suppress. A suppression marker is acceptable only when genuinely unavoidable, and then it carries an inline justification comment on the same line — the checker inventories every new one.
- Run the project formatter on files you touched before finishing (formatting is tooling's job, and it keeps style out of review entirely).
- Exact dependencies: every import you add is used; every package you use is declared. Remove imports your change orphaned.
- Changed files meet full strictness — you do not add code below the analyzer bar even if the surrounding file predates it.
- One logical change per cycle. Your final report explains why, not just what.

## checker

- Analyzer output at maximum configured strictness is the contract: new warnings in changed files are FAIL, not advisory.
- Inventory every new suppression marker in the diff (`@ts-ignore`, `# noqa`, `# type: ignore`, `eslint-disable`, `@SuppressWarnings`) with its justification comment or lack of one — an unjustified one is a tamper-adjacent finding.
- Ratchet accounting: count legacy violations in untouched files at baseline and now; growth is FAIL.
- Verify formatting: an unformatted diff (formatter would change it) is a FAIL with the exact command to run.
- Flag unused imports and undeclared dependencies introduced by the diff.

## spec-reviewer

- Missing behavior is FAIL; unrequested features are FAIL. A diff that quietly "improves" adjacent code violates the atomic-change rule.

## code-reviewer

- Review logic only: correctness, error handling, interface contracts, concurrency. Style and formatting comments are forbidden — if style bothers you, the finding is "formatter config gap", not a nit on the diff.
- Judge the commit story: is this one semantically atomic change a future reader can understand from the ledger entry?
