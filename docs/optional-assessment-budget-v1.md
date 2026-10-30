# Optional aggregate assessment budget

Scope: implement the October 30, 2026 operator request to remove the budget
ceiling for assessment `4055396e-35c0-4962-ba39-cf23e443ad8d`. New assessments
retain their $100 default. This is an operational authorization amendment, not a
scientific protocol change or evidence of claim correctness.

Only explicit SQL/JSON `null` means unlimited; missing, zero, negative, string
and nonfinite values are invalid. Finite ceilings can be restored at or above
recorded commitments. Original prompts, counters, usage, outcomes, source bytes,
scientific criteria, deadline, cancellation and per-invocation resource bounds
remain in force. Provider quotas and unknown-outcome fences remain enforced.

The service-only `research_autonomy_set_budget` RPC records an append-only,
same-transaction amendment and supports idempotent request identities. An optional
resume releases only budget-stopped tasks without running/unknown original calls.
It never replays blocked, cancelled, waiting or terminal work. The migration alone
changes no effective assessment limit or status. Browser SQL and RPC writes stay
denied; public queue projections report the explicit ceiling and retained usage.

Release review added a PostgreSQL regression for a raw `unknown` dispatch with
an already validated append-only reconciliation proof. The initial resume query
incorrectly excluded that task together with genuinely uncertain work; the red
test and actual database observation are retained. The corrected query admits
fresh work only when the proof matches dispatch, assessment, task and original
request hash. Original unknown receipts remain immutable. A separate genuinely
uncertain task remains fenced. The first added fixture also correctly failed
until its original proof/checkpoint records were appended to the database; that
failed setup is retained and is not evidence of a production defect.

Before changing production, run the isolated PostgreSQL test, backend regressions,
frontend validation and build. Verify AWS account `395567831870` and Supabase
project `regphejnlvfpyokpniny`. Release nullable-aware frontend and backend with
admissions held before applying this assessment's explicit amendment. Renew the
exact-source runtime qualification/approval and retain deployed verification.
The original assessment deadline must not be extended to accommodate rollout.

Declared local pass criteria, before the new checks run:

- An unaudited cap change, browser RPC, conflicting replay, commitment refund,
  deadline mutation or cap below retained usage is rejected.
- Default funding remains $100; an explicit unlimited amendment preserves prior
  usage, original request/hash, deadline, task counters and scientific labels.
- Actual controller SQL admits and records reservations above the former cap;
  restoring a finite cap enforces it. No provider calls or charges are simulated
  as real measurements.
- Budget-only resume retains checkpoints and skips uncertain or blocked work.
- Worker prompts and owner/public UI distinguish explicit unlimited from zero
  or absent limits. Finite exhaustion still permits only a blocked decision.

Tests are exposed development checks by the implementing AI, not independent
or human scientific review. No new cloud instance, experiment or model call is
needed for local validation; charges and subscription allocation remain unknown.

Local results: 398 backend tests, 278 frontend tests, all three PostgreSQL check
groups, the actual PostgreSQL/API-to-frontend validator round trip, the frontend
production build and scoped frontend lint passed. The sandbox-blocked first SQL
attempt and subsequent successful reports are retained separately. The private
local archive and retrieval-verified member hashes are indexed by
`optional-assessment-budget-local-v1-status.json`; production authorization and
Supabase evidence retention remain pending the compatible release.

Reproduce from the named checkout:

```sh
# jumpserve-infra (isolated localhost PostgreSQL required)
npm run test:research:optional-budget
python3 -B bin/retain-optional-budget-local.py
# jumpserve-back-end
python3 -B -m unittest discover -s research_workflow/tests -v
# jumpserve-front-end
npm test
npm run build
```
