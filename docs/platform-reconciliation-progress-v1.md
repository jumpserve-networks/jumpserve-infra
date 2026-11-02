# Supervisor HTTP recovery and fair reconciliation

Status: deployed on 2026-11-02. The [production record](platform-reconciliation-production-20261102.md)
contains exact revisions, qualification, installed-source verification and the
observed automatic reconciliation of the original HTTP 503.

The 2026-11-02 audit found task `910739f6-118c-47ea-ab3e-ddd70b8efe34`
repeatedly reclaiming the shared host after its original deadline. Native call
`0f09c104-0827-4be8-a419-b691f57854b2` retained `Provider HTTP 503.` with an
original `unknown` outcome and no supplemental reconciliation. The worker could
only reconcile successful terminal responses, and the scheduler prioritized all
`reconciling` tasks ahead of independent repairs. A fresh heartbeat did not mean
that this recovery path was progressing.

## Retained evidence and supplemental outcomes

The native coding bridge buffers the complete provider response before delivering
any bytes to OpenClaw. On non-success HTTP responses it records the original
bytes and raises before returning them to the local tool runner. Its request
contains only the five local function tools; stored responses, background work
and provider-hosted tools are excluded from this recovery adapter.

`platform_supervisor/call_recovery.py` verifies the original request, response and
receipt bytes against the original run and private artifact metadata. Only exact
HTTP 500, 502, 503 or 504 receipts from this buffered function-only transport can
receive a `platform-native-http-reconciliation-v1` certificate. A status code or
error message alone is insufficient. Error-body text is untrusted original data.

Migration `202611020001_platform_reconciliation_progress.sql` admits that
certificate through the service-only `reconcile-http-error` worker operation.
It requires a live task lease, the exact original terminal unknown identity,
three task-bound artifact references and a matching retained certificate. It
appends one immutable `platform_run_reconciliations` record and a
`model-http-error-reconciled` event. Concurrent identical submissions are
idempotent; altered proofs are rejected. Previous RPC implementations remain
private and cannot bypass admission.

The supplemental outcome says this coding response failed without delivering
tools. It does not assert that the provider performed no processing or charged
nothing. The original `unknown` row, usage, reservation, request, response and
receipt stay unchanged. No original request is replayed. A later coding turn is
subject to the existing admission, funding, cancellation and deadline gates.
Failure alone cannot certify a proposal, release or experiment as complete.

Partial HTTP 200 streams, missing evidence, hash mismatches, unsupported tools
and transport timeouts retain their existing uncertain-call fences. Paused,
cancelled or expired tasks can record the outcome of an already admitted call;
the adapter cannot authorize new coding or restore their deadlines.

## Independent repair progress

The migration changes only the scheduler's task selection order. Shared container
cleanup, unresolved external mutations and running model calls retain urgent
priority. Ordinary task-local unknown calls rotate alongside independent tasks
at the same priority, using the least recent claim. Assessment-repair priority
remains ahead of general maintenance. Host reservations, research cooldowns,
single-lease admission and uncertain external-operation guards remain intact.

After container cleanup and workspace validation succeed, an unchanged
task-local model blocker records a `platform-reconciliation-backoff-v1`
checkpoint. Probe intervals are 60, 120, 240, 480, 960 and then at most 1,800
seconds. A changed retained-evidence fingerprint resets the interval at the next
probe. This backoff does not resend a provider call or clear its fence. Cleanup
uncertainty and pending or unknown external operations cannot use this deferral.
The worker still runs its existing claim loop; task-local waiting does not occupy
a coding lease between turns.

## Verification and release

Run the supervisor tests from the backend repository:

```sh
python3 -B -m unittest discover -s platform_supervisor/tests -p 'test_*.py' -q
```

Run the database suite from the infrastructure repository against the existing
isolated loopback PostgreSQL test server:

```sh
python3 -B test/check_platform_reconciliation_database.py
```

The SQL suite retains the preceding 93 funding, controller, incident and scheduling
checks, then exercises the new migration and actual concurrent worker RPCs. The
supervisor regressions include the actual local HTTP bridge with synthetic
provider transport, original-byte validation, restart deferral and stopped-task
admission. These are software checks, not scientific findings or proof of live
unattended completion. They create no provider calls or production mutations and
do not require local Docker containers.

For an explicitly requested release, apply the migration through the existing
project-locked path before installing the qualified supervisor bundle containing
`call_recovery.py`, `native.py` and `worker.py`. The bootstrap migration manifest
and CI database entry point include this migration. No frontend build, new AWS
host, credential, IAM extension or research-runtime pin is required by this fix.

Verify the exact deployed bundle and schema, original artifacts and supplemental
event, then observe an independent repair acquiring a turn and doing useful work.
An expired original repair should reconcile and retain its deadline outcome;
this migration does not revive it. Record remaining blockers and assessment
measurements separately. Heartbeats, a supplemental failure or passing local
tests cannot establish end-to-end paper reproduction.
