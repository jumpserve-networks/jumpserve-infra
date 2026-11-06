# Captured provider failure recovery

## Failure and resulting behavior

Two capability tasks were retrying a changed `assessment-evidence-v1` request
under an already recorded parent/profile. The database correctly retained the
original request, but returned HTTP 400 instead of representing the additional
requirements. A generic schema/evidence activation also did not establish that
worker source delivery or native spool inspection had been implemented.

The forward migrations retain the changed requirements as immutable service
refinements. The supervisor receives a typed `requires_implementation` result,
keeps the original activation and artifact identities, and continues from the
explicit implementation feedback. It cannot certify a new capability by
reactivating the same manifest.

The worker now records bounded observations of its five fixed recovery source
files and the exact original dispatch's native response/completion files. The
report distinguishes missing, inaccessible, unsafe, oversized and captured files.
A private service-only observation registry authenticates these reports. An
owner-written artifact label alone cannot enter the supervisor's trusted view.
Original bytes remain private; safe views identify original and projected hashes
separately. Observations neither reconcile a model call nor claim experimental
completion.

## Reconciliation contract

`captured-provider-failure-v1` accounts for an original failed buffered response
only when the retained request, response, transport metadata and explicit error
agree. HTTP 429/500/502/503/504 require the captured JSON error. HTTP 200 requires
a complete SSE error frame before any completed/incomplete terminal event. A
partial tail after that frame is allowed because the buffered bridge already
raised before forwarding the response to its tool runner. CRLF prefix offsets
refer to the original bytes.

Native admissions must already be `failed`. Controller admissions must be failed
data-only requests with no native call, matching original turn/request/receipt
and four dispatch-bound artifacts. Supplemental records are immutable and
idempotent. Original failures, usage, reservations, deadlines, request identities
and scientific criteria remain unchanged. A controller failure is not an accepted
decision. Native workspace recovery still requires complete call coverage and
confirmed container cleanup before ordinary resume admission can run.

Unknown calls without original response evidence remain fenced. Missing bytes
are not proof of non-execution, provider charges remain unknown, and no provider
request is replayed by this adapter. The retained unknown call 79 must be
inspected on the actual worker before its outcome can be determined.

## Qualification and installation

The dedicated `captured-provider-failures-v1` gate permits only the declared
recovery functions and one new regression file. Existing scientific, request,
transport, execution and test source stays exact. The former gate and fixed
checks remain unchanged; the new driver verifies the former driver's hash and
runs all its checks before its additional failure check, without credentials,
network or inference.

Backend main includes other changes after the installed research runtime pin.
`captured-provider-overlay-v1` therefore composes only `dispatch_recovery.py`,
derived approval metadata and the new regression on the exact frozen base.
The pin records that base and all installed file hashes. Asset preparation and
independent release qualification reproduce those bytes without overwriting
backend main or silently releasing unrelated source.

Research runtime release verification now covers the three controller Lambdas
and the AWS OpenClaw research worker. A service-only installation intent drains
active research and holds new admissions for a bounded maintenance window. It
admits one exact SSM command; a missing acknowledgment is reconciled against
that command and cannot trigger a replacement. The installer verifies the real
worker predecessor before stopping it, verifies the bundle, atomically switches
versioned runtime directories, retains the prior source for rollback, and checks
the service PID's working directory and installed hashes. Spool and credentials
are hashed before and after switching, before normal service startup. Those
files are neither printed nor replaced. The supervisor runtime stays separate.

If predecessor hashes differ, installation stops before switching. The actual
worker source must then be retained and qualified; an authorization or an updated
Lambda pin does not establish successful worker installation. A partial release
must not be marked verified. Reconcile its original CloudFormation and SSM
identities rather than dispatching another release.

## Release order

Initial qualification used local isolated PostgreSQL and the existing AWS tool
image in containers without network or credentials. Follow the order below for
production installation after an explicit deployment request under AGENTS.md.

1. Merge the qualified backend support and recovery source before infrastructure
   validation; the new database regression explicitly tests protected backend
   main, while asset preparation continues to verify installed runtime pins.
2. Apply the forward migrations in order: `202611060002`, `202611060003`, then
   `202611060004`. They retain original calls and task records and keep browser
   access denied for the new private relations and RPCs.
3. Install a qualified supervisor bootstrap bundle containing its new service
   refinement handler and the dedicated gate/check assets. The ordinary
   self-update profile cannot install new frozen external qualification assets.
4. Qualify and publish the isolated recovery source and its derived approval,
   certificate and research runtime pin. Run the exact protected research runtime
   release through the existing renewable GitHub OIDC role. Record both controller
   and worker readback before declaring production verification.
5. Inspect worker observations and supplemental reconciliation events. Resume
   only through ordinary existing admission checks. Preserve any genuinely
   unknown outcome and its original blocker if the retained spool is insufficient.

The native worker inspector and supplemental records are read/reconciliation
work; neither resets a limit nor changes an assessment's scope.

## Verification

- Backend research tests on the isolated frozen-base candidate, plus supervisor
  tests and the fixed independent qualification driver.
- `python3 -B -m unittest discover -s test -p '*runtime*test.py'`
- `python3 -B -m unittest discover -s test -p captured_failure_worker_test.py`
- `npm run test:platform:provider-recovery` runs the complete existing database
  lifecycle chain plus captured failure, refinement, privacy, unknown-outcome
  and worker handoff regressions against isolated PostgreSQL only.

The local private evidence report `observed-failure-validation.json` recognizes
the three retained failures and preserves the fourth call as unknown. Test and
evidence validation made zero provider calls and zero production mutations.
