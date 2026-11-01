# Controller terminal evidence and source-reader recovery

This change addresses two observed operational blockers in assessment
`444d171c-2fac-4ba9-b33c-2b46304cb0ec`. It is software validation by the
implementing AI, not independent review, a scientific finding, or proof of
unattended completion in production.

## Original failures

Dispatch `970716c3-1869-5ee9-a4bf-8bf6c92c70d7` retained a complete, consistent
terminal response from `gpt-6.1-sol`. Its decision failed strict inspection UUID
validation. The existing builder recovery adapter could not account for an
ordinary controller rejection. This left repair diagnosis waiting despite
having the original logical request, provider request, receipt, and response.

Task `9d92d0c9-c423-5d7f-9298-bccf4bca1b35` stopped with
`Evidence page byte budget is outside the reader bound.` Source rereads copied
the larger initial inline transport into a smaller page envelope, leaving no
room for actual fragments. Its earlier repair record was already resolved, so
ordinary discovery could not reopen that same incident. The supervisor had
retained a narrow reader fix but had not qualified and released it.

The private repair view also omitted original controller transport artifacts,
`project/acquisition.py`, and imported project helpers, making these incidents
harder to reproduce from delivered evidence.

## Changes and boundaries

- `dispatch_recovery.controller_terminal` requires four hash-verified originals,
  the exact logical/provider request mapping, strict transport fields, one
  completed and consistent terminal stream, the expected model, a rejected
  decision, and no native admission for that dispatch. HTTP 200 or a receipt
  alone is insufficient. It does not accept an unknown dispatch or a valid
  decision, reuse the rejected decision, invoke a model, or claim cleanup.
- Migration `202611010009_controller_terminal_recovery.sql` provides a
  service-only, idempotent supplemental proof RPC. Original dispatch, parent
  turn, usage, and authorization records remain unchanged. Concurrent workers
  produce one immutable record. Task quiescence and study, task, request, and
  artifact identities are checked under the existing locks. Browser callers
  cannot reconcile calls or invoke the private admission predicate.
- Source rereads omit only duplicated initial inline fields. Actual text,
  fragment hashes, page cursors, source ownership, byte bounds, and incomplete
  coverage remain intact. The runtime scope gate recognizes this exact AST
  change; edits to authentication, fragment selection, or byte budgets still
  fail the frozen-content check.
- Verified runtime resumption recognizes the two exact reader failures and
  supplemental closure. It still requires the verified runtime release and
  matching pin, original deadlines and cancellation checks, current category
  budgets, and no unresolved calls. The existing once-per-source-binding guard
  prevents repeated restarts. Prompts, criteria, labels, attempts, and task
  context are retained.
- Migration `202611010010_controller_incident_evidence.sql` prioritizes the
  dispatch named by the immutable blocker and delivers original logical,
  provider-request, response, and receipt references within the existing
  twelve-artifact cap. Passive response views show terminal identity and the
  rejected assistant decision without promoting them into authority. Project
  source views include up to 32 eligible additional files with explicit
  omissions, original hashes, existing redaction, and archive safety limits.
  Nothing from an incident archive is executed.

Genuinely incomplete native call `7fee4473-a910-4f48-8415-e5e444411f00`
remains unresolved. This change supplies no missing terminal bytes and cannot
authorize replay of that call.

## Local verification

Run from `jumpserve-back-end`:

```sh
python3 -B -m unittest discover -s research_workflow/tests -q
python3 -B -m unittest discover -s platform_supervisor/tests -v
python3 -B ../jumpserve-infra/assets/platform/research-runtime-checks.py
```

Run from `jumpserve-infra`, using the documented isolated loopback PostgreSQL
fixture, or `UNLIMITED_DEFAULTS_TEST_DATABASE_URL` for an isolated local service:

```sh
python3 -B test/check_controller_terminal_database.py
python3 -B -m unittest discover -s test -p source_reader_gate_test.py -v
python3 -B -m unittest discover -s test -p '*release_test.py' -v
python3 -B test/check_controller_terminal_retained.py
npm run build
npm test -- --runInBand
```

The SQL suite retains all 76 predecessor checks and adds eight real PostgreSQL
checks covering original preservation, concurrent closure, caller denial,
quiescence, cross-study refusal, incident evidence delivery, qualified
resumption, and unchanged uncertain calls. Its RPC fixture is independent of
the new runtime implementation, so CI can run against the existing pinned
backend. Backend controls and the retained-original control exercise the
actual byte validator separately.

The retained control requires the ignored, previously downloaded originals in
`.test-artifacts/controller-terminal-v1`. It checks fixed hashes without
printing private prompts or raw responses, executes no archived source, and
compares runtime changes against the exact pinned baseline. A missing original
is a failed control, not permission to manufacture a replacement. Original
bytes, failed test reports, and successful reports stay outside commits.

Infrastructure synthesis tests require assets prepared from the exact current
pin. Candidate runtime bytes must not be copied under an older manifest.

## Release requirements

No production change is made by these local checks. On an explicit deployment
request, qualify and pin the exact new runtime source and supervisor bundle,
apply migrations 009 then 010 through the reviewed project-locked migration
workflow, and publish the controller/worker code through the existing scoped
release adapters. Generate fresh source-bound qualification metadata; the old
runtime approval is not evidence for these new bytes. The bootstrap migration
list and required CI entry point include both forward migrations and the new
regression suite.

After a verified runtime release and matching pin exist, use the existing
`research_runtime_resume` adapter for eligible retained reader failures.
Observe the exact supplemental proof, ordinary repair diagnosis, a new recorded
execution step, and resulting persisted measurements before claiming live
recovery. A passing local control alone does not establish that the production
supervisor has completed an autonomous repair or assessment.
