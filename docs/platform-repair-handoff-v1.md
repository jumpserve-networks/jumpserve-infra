# Assessment repair evidence and blocked progress

Implemented and verified locally; production activation is recorded separately
in private Platform Updates. This extends the existing
[assessment blocker flow](assessment-blocker-repairs-v1.md).

The [semantic evidence and queued-admission follow-up](platform-repair-recovery-v2.md)
addresses a nested timing field found in production and adds trusted recovery for
unclaimed admissions whose original controller turn ended.

The observed platform repair repeatedly ran local checks and wrote logs while its
own `progress.json` said that original incident evidence was unavailable. The
controller supplied a short trigger diagnostic and treated every incomplete slice
as `implementing`, including an explicit blocked report. A healthy heartbeat and
successful provider calls therefore did not establish repair progress.

Migration `202611010001_platform_repair_context.sql` supplies a service-only RPC
bound to the current worker, task lease, authorization and immutable assessment
repair link. It returns a coherent snapshot of the linked blocker, research task,
repair incidents/events, dispatches, native calls and reconciliations. Records and
detail sizes are bounded and coverage totals are explicit. Unresolved calls take
priority over completed history, and referenced checkpoints take priority over
recent transport artifacts. Browser roles and direct helper invocation are denied.

The platform controller retains the original packet privately and delivers
redacted, hash-linked views under `references/assessment-repair/`. It retrieves
only selected diagnostic artifacts from the fixed private research bucket,
verifies their original byte counts and hashes, and projects selected source files
from bounded checkpoints without executing them. The model receives no service
credential, private storage pointer or direct database tool. The summary directs
it to inspect only necessary details and to preserve unknown outcomes.

A bounded regular `progress.json` with version `platform-progress-v1`, `ready:
false`, `status: blocked` and `remaining_blocker` requests a conservative stop.
The bridge rejects the next inference before reservation or transport. Separately,
two incomplete slices without substantive implementation changes stop the repair;
new `.log`, `.md` or `.txt` files do not clear this detector. These are local
software-progress guards, not limits on assessment spending or scientific criteria.

Blocked repair state persists in the original task checkpoint. Maintenance checks
for changed incident evidence in the ordinary worker loop, with no daily schedule
or timer-only retry. A changed diagnostic, source artifact or recorded call outcome
can reactivate the same task. Lease renewals, heartbeat clocks, spent counters,
repair phase revisions and duplicate timestamp-only events do not. Previous blocked
progress is retained when a fresh evidence version permits another attempt. Task
IDs, commitments, model-call counters, original deadlines and uncertain outcomes
are preserved. Pause, cancellation and expired/stopped parent assessments remain
effective. Existing private Platform Updates task reasons/events expose the state.

After an explicit deployment request, apply the incremental migration to JumpServe
project `regphejnlvfpyokpniny` after the existing native-call reconciliation and
maintenance migrations, then install the reviewed platform worker source bundle.
The bootstrap migration list includes the new RPC for future installations. Use
the existing host maintenance, exact-source and production readback procedures;
do not rerun owner enrollment or reset existing task checkpoints. No frontend
release, new AWS role, provider call or research-runtime pin is required by this
change. Production repair success must still be observed after activation; local
tests do not establish unattended completion of the live assessment.

Verification entry points:

- Backend: `python3 -B -m unittest discover -s platform_supervisor/tests -v`.
  The credential-free suite includes an actual loopback HTTP bridge, stopping
  before a second reservation, controller restart, changed-evidence recovery,
  redaction, original artifact checks and source-progress regressions.
- Infrastructure: `python3 -B test/check_platform_repair_context_database.py`.
  This runs the existing funding, maintenance and native reconciliation checks
  before the new migration in a retained isolated loopback PostgreSQL fixture.
  It verifies immutable original rows, role/lease scope, checkpoint priority,
  cross-assessment exclusion, stable evidence fingerprints and same-task recovery.
  The infrastructure Platform validation workflow runs this combined entry point.

These tests start no Docker containers, invoke no model and mutate no production
resources. Local PostgreSQL and the HTTP bridge require loopback socket access.
