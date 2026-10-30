# Unlimited assessment budget release

Status: production rollout in progress. Frontend `4044bc6` passed Amplify job 131.
Backend `a04b0c7` is pinned by runtime manifest 74 (59 files), including the
qualified `09cfc7d` implementation and its renewed recovery approval. All 99
infrastructure tests and TypeScript compilation passed. The final deployed
receipt will be `optional-assessment-budget-production-v1-status.json`.

The operator explicitly authorized an unlimited aggregate budget for assessment
`4055396e-35c0-4962-ba39-cf23e443ad8d`, then requested merge and production release.
Only this assessment is amended. New assessments retain the $100 default. Explicit
null means unlimited, not zero, missing data or unknown authorization. Commitments,
available usage, original prompts, source and task identities, scientific criteria,
the original November 4 deadline and unknown provider outcomes remain retained.
Per-call resource limits, provider allowances, cancellation and no paid fallback
remain enforced. Unknown monetary charges are not represented as zero.

Local qualification passed 398 backend tests, 278 frontend tests, the production
frontend build, scoped lint and actual PostgreSQL-to-public-API-to-frontend
validation. SQL checks demonstrate audited/idempotent amendment, reservations
above the former cap, reinstatement of an enforceable finite ceiling, retained
usage/deadline, browser-write denial and safe budget-only resume.

Release review added a real PostgreSQL case with an immutable raw unknown dispatch
and a matching append-only reconciliation proof. The initial resume query left
that proven-recoverable task stopped; the failed test and database observation
remain retained. The corrected query verifies dispatch, assessment, task and
original request hash before allowing fresh work. A truly uncertain task remains
fenced, and neither original receipt is rewritten. The first added fixture failed
until its original proof/checkpoint records were appended; this setup failure is
preserved separately from the demonstrated resume defect.

The initial Linux campaign passed all 23 installed-native and budget/recovery
tests with no skips but was paused before any real provider call for the SQL
correction. Its archive SHA-256 is
`549c1f6a99f1387f4b7ae213f1081ee9a107440d9cd694fc0b60554c02effe5b`.
A separately frozen follow-up retains identical backend runtime bytes and the
proof-aware SQL/local evidence. It repeats the 23 Linux controls and allows only
one actual subscription response, reserved at 100 cents, for a missing-source
software fixture under explicit unlimited authority. This response must remain
blocked for missing data with no invented claim, evidence, proposal or scientific
finding. The qualified builder/netem/credential/dispatch implementations are
inherited only after exact file hashes match the previous release. These are
exposed software checks reviewed by the implementing AI, not human, independent
or held-out scientific validation.

The follow-up passed all 23 Linux checks without skips. Its actual subscription
answer was reviewed in full: blocked/missing-source-data, no claims, evidence,
proposal, scientific label or complete coverage. It completed in 28.75 seconds
with 3,807 input and 90 output tokens, no provider retry and no paid fallback.
The original request includes the explicit unlimited authority and null ceiling.
Its private archive was retrieved and hash-verified as
`c8d5df65ed18cc5004c9d061fbc533ea4ab306036a84849261957daf656d5c1f`.
Both the paused pre-provider campaign and passed operational evaluation are
retained against the existing published prompts; prompt publication was unchanged.

Admissions and polling are held during migration and runtime replacement. Apply
the financial amendment only after exact deployed backend/worker hashes, RLS and
browser RPC/write denial, executor assets and the matching frontend release pass.
The existing worker, grant, pinned image and encrypted 300 GiB volume are retained.
An uncertain amendment response is reconciled against its original immutable
request event instead of issuing another funding identity or resume operation.

Scientific assessment coverage is separate: unlimited funding does not resolve a
method, implementation or reconciliation blocker. Record actual post-release
claim/job progress without restarting the assessment or changing its criteria.
Fresh authenticated uploads/chat require a legitimate browser session; unchanged
flows are reported as unverified if unavailable.

The fixed-target release entry point is `bin/optional-budget-release.py`; its
protocol is `optional-budget-release-protocol-v1.json`. Dispatch each qualification
phase once and use `status`/`collect` to inspect original results. After actual
answer review, record it, approve the exact source, pin/stage, run infrastructure
checks and review scoped CDK diffs. Migrate, deploy held, verify, apply the audited
budget, activate, verify public/browser state, then retain the hash-verified
private production artifact. Raw prompts, responses, protocols, failed checks,
migrations and retrieval manifests remain in the evidence archives.
