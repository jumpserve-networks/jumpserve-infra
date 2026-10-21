# Unlimited autonomous AI turns: local implementation

The application candidate removes the AI turn-count limit for paper intake and
individual claims. The $100 aggregate paper commitment limit and seven-day
elapsed deadline remain. Turns remain numbered, charged conservatively and
recorded with exact requests, responses, prompt versions, hashes and available
usage. Unknown usage/cost remains unknown. Parallel capacity is unchanged.

The worker, SQL admission/constraints, context recovery, API validation, PDF
intake confirmation and queue display support the new policy. A null ceiling is
explicitly unlimited; missing/invalid counts remain errors. History stays bounded
per page and can paginate beyond turn 25. Older service status is readable with
its actual legacy ceiling; new intake requires the v3 capability, preventing a
new client from silently accepting a capped backend.

`database/202610200008_remove_autonomy_turn_cap.sql` archives previous ceilings in
immutable policy-change events and changes current workflow ceilings to null.
Original initial prompts, old turn records, findings, costs and deadlines remain
unchanged. The transaction temporarily disables only the workflow immutability
trigger for this controlled field migration, then restores it. RLS and browser
denials remain enabled throughout. Private lab audit tables, when installed,
also accept later turn numbers for future versioned campaigns.

The migration does not dispatch work. The matching worker calls the service-only
`research_autonomy_resume_turns` gate. It requeues only historical count stops
with remaining original time/budget and no uncertain provider or pending
experiment identities. It keeps the original task, stage, label, context and
counter, and records the prior stop before resuming. It does not restart
cancelled/completed/expired/exhausted workflows or generic external blockers.
Known provider failures requiring reconciliation stay retained.

The active historical prompt is not rewritten or republished. A versioned
trusted controller instruction explicitly supersedes its obsolete 25-turn
references. The complete instruction is stored in every actual request; the
processing receipt identifies `autonomy-turn-policy-v1`. This is a changed model
input configuration and requires actual-answer evaluation before claiming live
model behavior is verified. Prior publication evidence is not new validation.

Validation used exposed synthetic development cases, actual local Postgres,
the controller/queue/arithmetic implementations and actual browser components.
Authentication, provider answers, Storage and cloud SDKs are fixtures. No new
paper assessment, paid model request or remote database write was made.

- 177 backend and 198 frontend tests passed; 93 infrastructure tests passed with
  the backend checkout enabled. Backend tests exercise counts up to 1,000 and
  exact request retention; the actual SQL campaign admits 40 sequential turns.
- Eleven existing actual SQL/controller/worker groups passed, including parallel
  claims, atomic cost reservations, seven-day stopping, context recovery and
  bounded host-local TCP persistence. These are software checks, not paper claims.
- Six upgrade groups passed. Seven retained legacy workflows each admitted 25
  synthetic turns before upgrade. Full old turn rows and initial hashes compared
  equal afterwards. Only the eligible count stop resumed, its next turn was 26,
  and budget/deadline/cancelled/completed/blocked/unknown cases stayed stopped.
  Both optional private audit tables accepted 26 after rejecting it before the
  upgrade; zero and browser access remained denied.
- Eight PDF-upload SQL groups passed, including concurrency, hash checks,
  owner isolation and replay.
- Nine browser groups passed in desktop/mobile and light/dark views: PDF intake,
  invalid PDF, autonomous parallel progress, exact policy/prompt history, no-turn-
  limit display, blockers, missing/invalid status, navigation and real anonymous
  Next.js sign-in return paths. The browser auth/provider/Storage remain synthetic.
- Both TypeScript/Next.js builds passed. Frontend lint passed with the existing
  unrelated `auth-button.tsx` navigation warning.

The first unrestricted-loopback test attempt was blocked by the sandbox and its
failure report is preserved. The same scoped command passed with local network
permission. The initial infrastructure run skipped five backend-dependent tests;
the subsequent explicit-backend run passed all 93. The first passing upgrade
report remains preserved before the separately documented private-audit amendment.
Exact reports, logs, hashes and protocol references are in
`autonomy-turn-policy-validation-v1.json`.

Reproduce locally from the backend with
`python3 -B -m unittest discover -s research_workflow/tests -v`; from the frontend
with `npm test`, `npm run lint`, `npm run build`; and from infrastructure with
`python3 -B bin/prepare-research-runtime.py`, `npm run build`,
`JUMPSERVE_BACKEND_CHECKOUT=/Users/Shared/allstar/jumpserve-back-end npm test -- --runInBand`,
`npm run test:research:autonomy`, `npm run test:research:turn-policy` and
`npm run test:research:paper-uploads`. SQL tests require the isolated existing
Postgres cluster on loopback port 54477. For browser checks, start the existing
`npm run test:research:autonomy:browser-fixture` infrastructure fixture and a
frontend production server on port 6002, then run
`npm run verify:research:autonomy` in the frontend. These entry points retain
fresh timestamped databases/reports and make no live provider calls.

Runtime v31 is a local uncommitted development manifest, not a production
revision. No merge, push, deployment, remote migration or prompt publication was
performed. A future authorized release must pin committed source hashes, apply
the migration before enabling the corresponding worker and frontend, evaluate
actual amended requests under bounded cost/time, and verify authenticated
production storage/execution and eligible recovery. Production target identities
must be verified at that time. No live deployment status was queried here.

Original subscription pilot v9 remains an archived 25-attempt limited campaign;
its results and inconclusive controller label were not rewritten or resumed.
Any continuation needs a separate versioned protocol; this change does not
reset its budget or expired pilot window. Historical evaluation/publication
guards retain their frozen profiles instead of representing their exposed old
cases as independent validation of the new policy.

Primary implementer/evaluator/reviewer: Codex AI, not human or independent.
Actual provider calls and production actions are zero in this verification;
measured charges and local compute/storage allocations are unavailable, not
asserted zero cost. Scientific criteria and evidence coverage do not change.
