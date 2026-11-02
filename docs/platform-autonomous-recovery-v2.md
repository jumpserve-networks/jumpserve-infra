# Persistent assessment incidents and operational supervisor self-repair

Status: implemented and tested locally; production activation is pending. This
implements the owner's existing standing mandate, without another authorization
grant. It does not establish that an assessment resumed or produced measurements.

## Incident lifetime and bounded attempts

An assessment incident can outlive an individual six-hour platform task.
Migration `202611020002_platform_incident_continuations.sql` preserves the original
one-to-one incident link and appends `platform_assessment_repair_attempts`.
The existing 15-second maintenance loop can admit a follow-up for an unresolved
incident whose last attempt completed, expired, or reached a concrete operational
blocker. It does not reset the predecessor's status, counters, deadline or calls.

The next attempt's deadline is the earlier of six hours and the original
assessment deadline. Its model reservation and call admission include the entire
incident family's original runs. Finite category budgets therefore remain finite
across attempts; `-1` remains unlimited. Reservations are not measured charges.
Owner cancellation, stopped assessments, unresolved original platform calls,
pending/unknown external actions, live leases and uncertain cleanup retain their
existing fences. An unknown research call can be investigated, never blindly
replayed to obtain a result.

Admission is serialized and permits one live investigation per assessment claim.
Repeated polling, timestamps, lease renewals and diagnostic repetition counts do
not create more attempts. The continuation fingerprint includes semantic research
evidence, definite failed operations, trusted controller-fault fingerprints and
immutable original-call reconciliation proofs. A legacy terminal attempt without
a recorded baseline can receive one bounded follow-up. Subsequent attempts need
changed evidence. Existing wake paths cannot reactivate an attempt that already
has a successor.

Every attempt remains visible as a separate Platform Updates task. The
`assessment-repair-continued` event records predecessor, root, generation, carried
reservations/calls and the original assessment deadline. The private context RPC
delivers the bound predecessor checkpoint. Its hash, size, task identity and ZIP
members are checked before delivering a passive local copy. Archived instructions
and proposed code are untrusted data; no predecessor source is executed or
automatically certified as correct.

## Supervisor repairs and extensions

`platform_supervisor/self_runtime.py` gives operational supervisor changes a
dedicated qualification route. The coding task receives the supported capability
contract and frozen boundary from the trusted controller. Ordinary publication
still rejects supervisor changes. Only paths bound to the exact gate result can
use this route; mixed application/runtime changes require separate candidates.

The frozen gate in `assets/platform/supervisor-runtime-gate.py` preserves the
credential, authority, source publication, release broker and uncertain-call
kernel, including listed critical methods in the controller and native bridge.
Existing tests remain byte-identical. It supports changes to operational Python
modules and new passive helper modules, with new regression tests. This is an
operational self-repair capability, not unrestricted rewriting of its own trust
rules. Changes to the frozen kernel, service identities or qualification broker
continue to require their dedicated qualification path under the same standing
authority; they are technical work, not requests for another owner decision.

Unexpected controller faults produce bounded `supervisor-failure.json` evidence
and focused coding feedback. Exception text and locals, which can contain private
requests or credentials, are excluded from that model view. A separate private
original exception artifact retains the bounded traceback without local variables.
Repeated identical faults retain a stable fingerprint instead of manufacturing
new evidence.

The controller records the executed checks and derived certificate. Protected
GitHub checks must pass before the exact candidate merges. The
`supervisor-runtime-release.yml` workflow repeats candidate checks and the
predecessor's frozen supervisor tests inside a container without network or cloud
credentials. Source mounts are read-only. It obtains the existing OIDC release
role only after qualification.

Backend CI explicitly checks out the protected infrastructure broker asset, and
the isolated backend checker mounts the installed broker read-only outside the
candidate. Tests do not depend on a sibling repository happening to exist.

The workflow verifies the actual installed predecessor and original task-bound
certificate, then admits one installation through `platform_supervisor_install`.
An uncertain SSM acknowledgment is reconciled by the original operation/comment;
absence or ambiguity never authorizes another command. The broker validates
the original asynchronous deploy operation even after its short polling lease
ends. A single ten-minute maintenance handoff drains existing research/native
work. New platform leases and research/native admissions stay fenced through
readback, including cancellation after an install was admitted. Original receipt
reconciliation remains available. Polling cannot extend the reservation, and
dispatch requires enough time for the bounded install. Verified activation
releases the hold; expiry bounds an unfinished handoff. The fixed installer checks
the archive and every file, switches the versioned symlink, restarts only the
supervisor and verifies actual installed hashes. Startup/readback failure restores
the previous symlink and starts the prior service. Research runtime files are
checked for changes. The original deployment operation remains fenced until its
workflow receipt is reconciled, including after a process restart.

Migration `202611020003_supervisor_self_install.sql` keeps install intents,
command receipts and verified activation manifests private and append-only.
`platform_supervisor_runtime()` supplies the current verified source baseline for
later self-updates. A verified capability activation emits one operational
evidence event for active waiting/blocked claims; repeat acknowledgments do not
emit another signal. Installation does not imply experiment or scientific success.

## Initial activation and verification

This initial implementation changes a frozen broker and must first use the
existing explicitly requested deployment procedure. No production mutation is
performed by local verification or by generating a bootstrap packet.

1. Run the backend supervisor suite, the infrastructure release tests and
   `python3 -B test/check_supervisor_self_install_database.py`. The latter retains
   all preceding database regressions and tests the real SQL admission paths.
   Run infrastructure Jest checks and TypeScript build as usual. Qualify exact
   protected source revisions and the installed Linux bundle for the release.
   Merge the infrastructure broker asset before backend CI checks that consume
   it from protected infrastructure `main`.
2. Apply both new migrations through the project-locked migration path. Deploy
   the reviewed access-stack change: the OIDC release role gains Supabase service
   secret read and SSM access to the existing supervisor host. Coding containers
   receive none of these credentials or permissions. No instance replacement,
   public database grant, static AWS key or new owner enrollment is required.
3. Install the qualified bundle, including the new frozen gate asset, while
   preserving the existing service/spool and its uncertain action identities.
4. Prepare a fresh exact-source bootstrap packet after the protected backend
   revision is committed and merged. Run:

   ```sh
   python3 -B bin/platform-supervisor.py activate-self-runtime --packet <private-packet>
   ```

   The first invocation submits a bounded read-only source/service verification
   on the fixed existing host. Subsequent invocations collect that original
   command until terminal, then record the initial manifest only after exact
   hash readback and protected main checks pass. The source must be clean and
   match the packet. A lost database acknowledgment reconciles through the
   identical immutable initial manifest. This is initial activation, not a
   per-release owner approval requirement.
5. Resume the prior admission settings and observe a continuation linked to the
   still-active original assessment. Verify its predecessor delivery, carried
   usage, bounded deadline, coding/qualification and any actual release. Then
   verify the research controller's safe continuation and fresh Supabase
   measurements separately. Never equate an idle supervisor, completed patch,
   deployment receipt or inconclusive measurement with unattended paper
   reproduction.

Local tests use synthetic provider/cloud services and an isolated loopback
PostgreSQL database. They cover concurrent attempts, finite family limits, stops,
immutable evidence, failed-release/fault handoffs, exact activation records,
atomic switching, startup rollback and lost SSM acknowledgments. Live AWS
self-update, IAM activation and assessment recovery remain release verification
requirements; local passing results do not claim those outcomes.

Local verification on 2026-11-02 passed 105 supervisor tests, 514 research workflow
tests, 43 release-broker tests, 117 database checks, the infrastructure TypeScript
build and 100 Jest checks. Five existing optional Jest checks were skipped.
Deterministic packaging verified all 31 bundle files. No provider calls or
production mutations were made by these checks.
