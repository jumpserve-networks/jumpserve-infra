# Uploaded paper review, version 1

Scope: local candidate for PDF upload → preparation → private owner review →
explicit confirmation → autonomous claim work. Existing assessments and legacy
operator URL intake retain their behavior. No production release is authorized
by this implementation turn.

The first screen accepts only the original PDF. The server verifies its complete
bytes, size, signature and SHA256, retains a private original, and atomically
creates a preparation workflow plus a private review. The review URL is
`/research-verification/new-assessment/<assessmentId>` and requires Google
authentication. My Assessments resumes unconfirmed reviews there.

The durable intake worker extracts text with the pinned parser. An exact original
matching a retained plan reuses that plan's source-grounded inventory. Other
papers use exact-page/chunk grounded candidate quotes, with the existing
200-claim inventory bound. Title suggestions must match a source quote after
whitespace normalization, or use the conservative corroborated title parser.
Domain suggestions are AI interpretations supported by a source quote. Unknown
fields remain null and the owner can supply them. Extracted text, metadata and
model processing never establish substantive full-paper review. Missing visual,
scanned, table, equation and supplement coverage remains explicit.

Requests include `paper_review_version=research-paper-review-v1`; the metadata
schema and instructions are recorded in the existing numbered autonomous turn
request/response records. The published historical prompt is unchanged. New
metadata-controller behavior has not been live-model evaluated or published as
validated. Preparation shares the original $100 commitment limit and seven-day
deadline; confirmation resets neither usage nor time. No AI turn cap is added.

`research_paper_reviews` holds the current revision. Immutable private
`research_paper_review_events` retain every snapshot, including rejected claims
in the candidate inventory and the selected IDs, owner corrections, revision and
actor at confirmation. Original PDF identity, initial prompt, claims and other
scientific evidence stay immutable. A narrow trigger permits exactly the
confirmed title/domain to replace an unpublished uploaded draft's placeholders;
other assessment modifications remain forbidden. Browser SQL access is denied
and both new tables retain RLS. Public queue projections are unchanged.

Preparation seeds are withheld in SQL, behind a fenced intake lease. Triggers
also reject direct claim-task and experiment-queue inserts before confirmation.
Owner confirmation checks the exact revision, retained selection and original
authorization under the same transaction lock, stores the confirmation, and
admits selected tasks once. Duplicate identical confirmations replay; conflicting
or stale confirmations fail. Unselected candidates remain recorded. An empty
inventory, failed extraction, cancelled authorization or expired/exhausted budget
cannot start an assessment. The review screen reports these states and an AI
worker pause explicitly, without treating missing evidence as success.

## Development checks and criteria

The following exposed regression cases are declared in source before the final
campaign. They are development checks, not held-out validation. Reviewer:
primary Codex AI implementer; not human and not independent.

- Original PDF bytes, owner scoping, bounded signed permissions and lost-response
  replay remain correct; old automatic-start services fail the capability check.
- A real local PostgreSQL database and pinned parser produce a durable prefilled
  review from an explicitly synthetic provider response. Before confirmation,
  claim tasks and experiment jobs must both be zero. Wrong-owner, premature,
  stale-revision and cross-paper selection requests must fail.
- Three concurrent identical confirmations must create one task per selected
  claim, preserve original budget/deadline and retain immutable review history.
  Conflicting confirmations and post-confirmation edits must fail.
- Malformed metadata, false page/quote grounding, invented titles and missing
  metadata must not be silently accepted or replaced with filenames.
- The browser must exercise upload, review reload, metadata correction, claim
  selection, explicit confirmation, navigation and subsequent queue behavior.
  Review and intake must fit desktop/mobile and light/dark themes. Error,
  unavailable extraction and missing metadata states must be meaningful.
- Frontend unit tests, lint/type checks, build, backend unit tests and the focused
  SQL campaign must pass. Scientific discrepancies remain findings.

Commands (repository roots):

```sh
# jumpserve-back-end
python3 -B -m unittest discover -s research_workflow/tests
# jumpserve-infra; isolated local PostgreSQL at 127.0.0.1:54477
npm run test:research:paper-uploads
npm run test:research:autonomy:browser-fixture
# jumpserve-front-end; while the fixture is listening on 127.0.0.1:4104
npm run verify:research:autonomy
npm test
npm run lint
npm run build
```

Timestamped successful and failed SQL/browser reports, raw fixture artifacts and
screenshots are retained under each repository's `.test-artifacts`. They use
synthetic Google authentication, model answers and Storage transport; they do
not prove remote Supabase signed-upload enforcement, Google login, live model
quality or actual network/cloud execution. Model calls and cloud experiments
are zero in these campaigns; monetary charges are unallocated, not measured zero.

## Release conditions

Deploy the versioned migration before the v2 upload backend, autonomous worker
and frontend; no new API Gateway route is required. Drain running work for the
function migration and preserve deployed runtime/prompt bytes for rollback. The
working-tree runtime manifest is explicitly a local candidate and must be bound
to the final committed backend revision before release. Do not use historical
prompt evaluation receipts as evidence for the new metadata controller.

Release-blocking follow-up: bounded actual-model metadata cases (ordinary title,
ambiguous/missing title, multidisciplinary domain, exact grounding and source
instruction injection) must pass under predeclared case-specific criteria:
faithful title or explicit null; defensible quoted domain suggestion or null;
all accepted quotes on the supplied page; no instructions obeyed; no claim work
before owner confirmation. Preserve raw answers, prompts, usage and failed cases.
Then exercise a legitimate authenticated production upload/Storage/review/start
flow, verify deployed hashes and account/project targets, and publish a release
receipt. Current local regressions do not satisfy those conditional live checks.
