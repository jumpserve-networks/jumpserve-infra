# Central claims and testable findings: development protocol v1

Freeze: 2026-10-24, before executing the new development cases. This assesses
software behavior, not whether an AI's scientific classifications are correct.

The review presents typically 1–3 suggested central claims and 5–15 suggested
testable findings, with fewer/zero when unsupported. Every entry retains its
original claim ID, statement, source and location. Other extracted statements
remain accessible and can be manually classified. Counts are review-shortlist
limits, not evidence of complete coverage or a reason to fabricate findings.

The controller processes immutable candidates in source-record order, in batches
of at most eight records/12 KB. Prior shortlist labels are explicitly summaries;
original statements are never truncated or rewritten. Review organization shares
the paper's original $100/seven-day authorization, records every numbered model
request/answer, and does not start experiments. Existing unconfirmed reviews can
request organization; confirmed assessments cannot be rewritten or restarted.

Declared blocking checks:

- Cross-paper, duplicated, unexamined and overlapping group IDs are rejected.
- Original statements, units and source links survive grouping and confirmation.
- Empty/unsupported groups remain empty; no lower-count quota is enforced.
- A 184-candidate fixture is processed with bounded request sizes and complete
  candidate accounting; no silent loss is presented as complete source review.
- Explicit selections from either/both groups alone seed experiments. No entries
  are selected by default. Other candidates can be assigned by the owner.
- Versioned SQL preserves review history, idempotent confirmation, original
  budgets/deadlines, owner authorization, leases and browser write denial.
- A legacy unorganized review is labeled explicitly; it is never silently
  classified by row position, numeric type or an invented scientific judgment.
- Frontend unit/type/lint and desktop/mobile light/dark browser checks pass,
  including empty groups, missing organization, and selection persistence after
  confirmation. Database guards run against isolated local PostgreSQL.

Fixtures and reused regression cases are development checks, not held-out model
validation. Reviewer/evaluator: implementing Codex AI, not independent or human.
Actual-model taxonomy quality, duplicate-detection quality and prompt-injection
resistance need a separate bounded release evaluation with retained raw answers;
structural rejection tests alone do not prove these semantic properties. No
production data migration, model evaluation or deployment is authorized by this
protocol itself. Original successful and failed reports remain retained.
