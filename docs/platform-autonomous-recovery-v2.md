# Persistent assessment incidents and operational supervisor self-repair

Status: deployed on 2026-11-02. The [production record](platform-autonomous-recovery-production-20261102.md)
contains the exact sources, installed-runtime verification and observed automatic
follow-up admission. This implements the owner's existing standing mandate;
assessment recovery and future self-updates still require their own evidence.

## Incident lifetime and bounded attempts

An assessment incident can outlive an individual six-hour platform task.
Migration `202611020002_platform_incident_continuations.sql` preserves the original
one-to-one incident link and appends `platform_assessment_repair_attempts`.
The existing worker maintenance pass can admit a follow-up for an unresolved
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

Migration `202611020004_private_incident_continuation_context.sql` explicitly
removes inherited execution grants on the context helper. Browsers and direct
service calls cannot bypass the existing task/lease-checked worker RPC.

## Initial activation and verification

### Prepared capability acquisition extension (not deployed)

The 2026-11-04 source adds an automatic capability implementation loop in
`platform_supervisor/capabilities.py` and forward migration
`202611040003_supervisor_capabilities.sql`. This section describes prepared local
work, not the installed November 2 runtime or a proven production recovery.

When a coding turn writes a structured `capability-request.json`, the controller
retains its exact bytes before queueing linked implementation work. The parent
waits while a separate backend task implements a declared operational tool pack
and new regression tests. It inherits the parent's deadline, category policy,
and incident/capability family accounting. Concurrent or repeated submissions
cannot create duplicate implementations. Parent cancellation reaches child work;
unknown calls, pending external actions and uncertain cleanup remain fenced.

The implementation uses the existing frozen checks, protected GitHub revisions
and supervisor self-update workflow. The new registry only delivers tool files
whose module bytes match the verified installed supervisor manifest. A passing
proposal or local test cannot register a production capability. Activation also
requires the implementation task's exact confirmed deploy operation, verified
release and installed source record. Eligible parents resume automatically;
paused, cancelled, expired or uncertain work does not. A later unrelated blocker
cannot be cleared by replaying an old activation.

The first pack contract supports executable workspace tools and read-only
diagnostic collectors. A literal `CAPABILITY` declares its id, revision,
description, instructions and relative tool files. Tool scripts run through the
existing isolated `exec` tool. An optional installed `collect(context)` receives
the current task's evidence packet; `context.original(artifact_id)` retrieves
only indexed originals from that packet and verifies study, path, byte count and
hash. Derived collector results are retained privately and projected through the
existing credential/contact redaction boundary before model delivery. Candidate
modules and delivered scripts are never imported by the host before activation.
An installed collector's programming fault automatically requests its next
revision, with a sanitized stack and retained private original. Persistence or
original-identity uncertainty remains a reconciliation hold, not a code upgrade.
Implementation tasks skip optional collectors so a broken collector does not
prevent its own repair.

Once a verified capability is available, the controller archives the exact old
local stop and request as private artifacts before retiring them from active
workspace inputs. This happens once per activation, and does not rewrite a
provider outcome or scientific finding. Tool rollback or removal is detected by
installed-source readback rather than treating an old registry entry as current.

This is an implementation path under existing standing authority, not a new
owner permission exchange. It does not automatically confer an unavailable cloud
permission, add a database mutation API, or qualify a change to frozen scientific
or admission code. Those remain concrete service/release adapter work with their
own executed checks; a tool pack must not claim to have installed them.

Initial installation of this extension changes the frozen controller's wiring
and acquisition kernel. Use the explicitly requested bootstrap/release procedure,
apply the forward migration, install the qualified controller and gate together,
and record the new exact installed baseline. Subsequent operational packs use
the existing self-update route without another owner approval. Do not use the
old frozen gate to certify this initial kernel change or infer activation from
a mandate. Verify a live missing-tool request through actual self-installation,
parent resumption and fresh measurements separately before claiming unattended
production recovery. The prior Slack controls expansion is independent local
work and is not activated by this migration.

Local verification runs `npm run test:platform:capabilities`, the backend
supervisor suite, and the infrastructure release-broker tests. They use explicit
synthetic install/provider receipts and retained local PostgreSQL, never a live
model, production mutation or a Docker daemon on the owner's computer.
The prepared source passed 116 supervisor tests, 133 database checks and 22
release-broker tests. Deterministic bundle SHA-256:
`99f1c035629e16587b81b3fd8286bbaf3dea2e4b59191c020f9cecdf125e929f`.
Protected-main CI, initial production installation and a live autonomous
capability acquisition remain separate verification requirements.

This initial implementation changes a frozen broker and must first use the
existing explicitly requested deployment procedure. No production mutation is
performed by local verification or by generating a bootstrap packet.

1. Run the backend supervisor suite, the infrastructure release tests and
   `python3 -B test/check_private_continuation_context_database.py`. The latter retains
   all preceding database regressions and tests the real SQL admission paths.
   Run infrastructure Jest checks and TypeScript build as usual. Qualify exact
   protected source revisions and the installed Linux bundle for the release.
   Merge the infrastructure broker asset before backend CI checks that consume
   it from protected infrastructure `main`.
2. Apply all three new migrations through the project-locked migration path. Deploy
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
tests, 43 release-broker tests, 118 database checks, the infrastructure TypeScript
build and 100 Jest checks. Five existing optional Jest checks were skipped.
Deterministic packaging verified all 31 bundle files. No provider calls or
production mutations were made by these checks.
