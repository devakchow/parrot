# stripe — role rubrics

## builder

- Treat every public surface (HTTP routes, exported functions/types, response shapes, event payloads) as a forever contract. Additive changes are fine; anything that could break an existing integrator must be versioned, flagged, or explicitly sanctioned by the task.
- When you touch the public surface, include an API design note in your final report: what changed, why the naming matches existing conventions (same verbs, same casing, same error shapes), and how old clients keep working.
- Type discipline ratchets up only: new files at the strictest level the project supports; never lower a file's strictness sigil/level; annotate what you touch.
- Update the docs/OpenAPI spec in the same cycle as the surface change (docs are part of the API, not a follow-up).

## checker

- Diff the public surface first: exported symbols, route tables, OpenAPI files, serialized response shapes. Report every surface change explicitly in its own list — the reviewers key off it.
- Backward-compat gate: if old-contract tests or recorded fixtures exist, run them against the new code; a removed/renamed public field or changed status code without versioning is FAIL.
- Type-coverage ratchet (only if the project already has the tooling): compare typed-ness before/after; any decrease is FAIL. Never install type tooling to enforce this.
- Fast CI or no CI: prefer targeted test selection per cycle, full suite before GREEN.

## spec-reviewer

- Missing behavior is FAIL; unrequested features are FAIL — especially unrequested public surface, which is forever.
- Verify the builder's API design note exists for any surface change and actually answers naming/consistency/versioning.

## code-reviewer

- Consistency review: new endpoints/fields must match existing naming, casing, pagination, and error-shape conventions — cite the existing example you compared against.
- Check error paths return the documented error shape; integrators parse errors too.
- Docs-travel: surface change without doc/spec update is a finding, not a nit.
