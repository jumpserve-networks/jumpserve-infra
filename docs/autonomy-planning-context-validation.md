# Source-grounded planning correction

Production update, 2026-10-22: the correction is deployed and verified, including
an actual authenticated PDF upload, four native AI turns, fresh reviews, one AWS
TCP execution and four persisted measurements. See the versioned
[production release record](planning-context-production-release-v1.json) and
[measurement check](planning-context-production-measurement-check-v1.json).
The pre-release findings below remain preserved as historical evidence; their
then-outstanding live verification gap was closed by the new declared campaigns.

Study `584e6ce7-b104-4f77-aa3a-2a2c0eac0f31` was cancelled at
2026-10-21 23:02:14 UTC, using the existing owner-bound cancellation RPC after
verifying AWS account `395567831870` and Supabase project
`regphejnlvfpyokpniny`. Its prompts, responses, source bytes and history remain
retained. The $86.95 commitment is a conservative admission reservation, not a
measured charge. No experiment jobs existed, and no new turns started after
cancellation. The final read-only check confirms cancelled status and zero
running turns. The study has not been resumed.

## Implemented behavior

Previously, source inspection returned source metadata even though extraction
had retained actual PDF text. Planning also received runner identifiers without
executable configuration schemas. The correction supplies hash-bound extracted
passages, exact claim anchors, paginated original page text, runner schemas and
prospective protocol shapes. Wrong source/study bindings, changed artifact bytes
and unsupported configurations fail closed. No scientific setting, package hash,
permission or experiment result is manufactured.

Reading progress is retained per task and review role, with a bounded summary,
original text identity and next undelivered cursor. Delivery does not establish
substantive review. Fresh reviews do not inherit another role's delivery or AI
verdicts. Figures, equations, scans, tables, reading order and supplements remain
explicit coverage limits. The controller's configured budgets, original
deadline, approval gates and unrestricted application turn policy are preserved.

A further check now rejects TCP protocols that omit its fixed RTT or byte-count
output or cannot budget both observations per exchange. Predicted success is a
comparison criterion; valid unexpected observations remain recorded.

## Validation and limits

- 198 backend tests passed, including source provenance, Unicode pagination,
  context size, source instructions, role-scoped delivery and complete TCP output.
- 95 infrastructure tests and TypeScript build passed.
- Eleven existing SQL autonomy groups and three new-paper integration groups
  passed against actual local PostgreSQL. A real PDF was parsed, separate fresh
  reviews admitted a prospective plan, and the actual loopback TCP executor
  returned four observations. Requests, responses, configurations, measurements
  and original executor bytes were persisted and hashes checked. Model replies,
  Google identity, Storage and AWS transport in this integration are explicit
  fixtures. It assigns no scientific verdict.
- A read-only check of the cancelled paper reconstructs all 15 extracted pages
  and delivers original quotes for all 52 retained candidate claims. The maximum
  actual v10 provider request is 45,673 bytes, below the 96,000-byte bound. This
  does not establish completeness of claim extraction or successful BBRv3 tests.

Fourteen native OpenClaw subscription calls were attempted under frozen,
amended development protocols. Every receipt records usage; actual charges and
subscription allocation remain unknown. No paid fallback or cancelled-study
model call occurred. These are exposed AI evaluations reviewed by the AI
implementer, without independent or human review.

The original four-case campaign strictly passed three immediate-answer checks.
The fourth legally requested source text; its failed immediate-proposal check is
preserved. A later trajectory repeated a read and stopped under its declared
rule. Adding delivery progress produced a source-bound proposal after three
further calls. Substantive review then caught the incomplete TCP output contract,
which is now enforced before execution. Those proposals must not be described
as validated executable plans.

The final two native checks did not demonstrate complete planning/execution:
one requested source text, and the other accurately identified the frozen local
contract's `executor_configured=false`. The evaluator rebuilt contracts outside
its declared synthetic-capability environment. This fixture defect is corrected
in the producer for future *newly frozen* campaigns; original requests/results
are unchanged. The fourteen-call evaluation limit was respected. No further
native call was made, and these results are not retroactively marked passed.

The original cancellation request is fulfilled and the local functional change
is implemented. Production still uses runtime 34; candidate runtime 35 is not
deployed or published. No prompt, database security policy or frontend is changed.
Before releasing this candidate, repeat a freshly declared live AI trajectory
with a correctly configured executor and verify the deployed request/response
and stored observations. Real BBRv3 ACK manipulation, exact kernel revisions,
paper-specific methods and missing external data remain separate dependencies.

## Reproduction

In `jumpserve-back-end`:

```sh
python3 -B -m unittest discover -s research_workflow/tests -v
```

In `jumpserve-infra`, with the backend checkout and local PostgreSQL available:

```sh
python3 -B bin/prepare-research-runtime.py
npm run build
JUMPSERVE_BACKEND_CHECKOUT=/Users/Shared/allstar/jumpserve-back-end npm test -- --runInBand
python3 -B test/check_autonomy_planning_inputs_database.py
npm run test:research:autonomy
```

Local TCP and native-provider bridges require permission to bind loopback
sockets. The development protocols v1–v7, real-source reports v1–v4 and the
artifact manifest preserve amendments, successful/failed checks, exact bytes,
configuration hashes and coverage limits. Historical provider producers retain
their frozen source snapshots and reject automatic replay. Do not rerun them
against a changed source or overwrite their results. A new live campaign needs
a new frozen directory and declared resources. Raw private study data and local
provider/authentication state are excluded from Git; the manifest contains
hashes and local locations, not credentials or a public artifact grant.
