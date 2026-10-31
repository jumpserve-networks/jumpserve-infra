# Immediate assessment blocker repairs

Status: implemented locally; production activation requires an explicit deployment
request for this change. This document does not claim production activation.

The platform supervisor should react when an assessment encounters a blocker.
General daily housekeeping remains a separate source of improvements. Migration
`202610310002_assessment_blocker_repairs.sql` adds a transactional outbox and an
adapter around the existing `platform_worker` RPC. No AWS role, worker image,
application runtime pin or frontend change is required.

## Event flow

1. A blocked assessment task, a repair diagnosis/wait/block, or a failed, invalid
   or uncertain model dispatch appends an immutable operational blocker signal in
   the same database transaction. A rollback also rolls back the signal. Normal
   experiment waiting does not create a platform repair task.
2. The same transaction emits a private `assessment-blocker-detected` Platform
   Updates event. Only identifiers, stage/status, a redacted bounded diagnostic
   and a hash of the unchanged original reason are copied. Original prompts,
   context, files, credentials and account/contact data are not copied.
3. On the existing 15-second service loop, the maintenance RPC admits up to eight
   retained signals as priority-zero repair tasks. This does not consume or check
   the daily general-maintenance slot. New signals can queue while other platform
   work exists; no lease or in-flight native action is preempted. Existing research
   dispatch priority and host fencing remain unchanged, so continuously occupied
   capacity can delay actual coding. The loop interval is not a pickup SLA.
4. The existing controller diagnoses, edits, runs fixed checks, publishes and
   releases only within the existing authority. The queued objective includes the
   assessment, claim-task and original source IDs and distinguishes a shipped
   correction from demonstrated assessment recovery. Existing release receipts
   and private events expose progress remotely.

Task-stage and normalized diagnostic text identify an incident. Repeated reports,
changing transport UUIDs/counters and competing drain requests cannot create new
task budgets for that same incident. A cancelled, exhausted or blocked platform
repair retains its original link and cannot be automatically replaced by repeating
the same signal. A different diagnostic or task stage can identify a new incident;
the classifier is conservative and is not proof of a common root cause across
different claims or assessments.

Signals persist during owner pause; task admission resumes only after the owner
resumes. Each repair retains a $100 conservative reservation cap and a deadline of
the earlier of six hours or the assessment's original deadline. There is no new
assessment spending cap. These are platform task reservations, not actual bills
or an aggregate AWS cost cap. More incidents can result in more bounded tasks.

Cancelled, exhausted, expired and fully completed assessments do not admit new
repairs. If a parent assessment stops after admission, the existing lease boundary
returns cancellation and new coding/publication admissions are fenced. In-flight
release/call identities can still reconcile. The adapter never resumes an
assessment, changes its limits or labels, retries an uncertain call, replaces a
failed observation or changes frozen scientific criteria.

SQL, worker, evaluated research runtime and protected configuration changes still
need their dedicated qualification/release procedures. Immediate triage does not
make every blocker repairable by the current release adapters. An external
prerequisite or unsupported release path remains an explicit retained blocker.

## Activation and verification

After a new explicit deployment request, publish the reviewed migration and checks
through the protected infrastructure repository. Apply only this incremental
migration to JumpServe project `regphejnlvfpyokpniny`, using the fixed-project
administrative transport. The connected Supabase MCP must first be checked for
its target project; do not use a connection to another project. This change does
not require rerunning initial bootstrap, reenrolling operators, changing the
standing model policy, deploying application stacks or restarting the AWS worker.
The bootstrap migration list includes it for future fresh installations.

Activation backfills existing active blocked tasks, active/waiting/blocked repair
records and uncertain/failed dispatches whose tasks remain blocked or waiting.
Existing historical failures on finished tasks and stopped assessments are not
reopened. Verify actual signal IDs, unique task links, priority, limits, heartbeat
and private dashboard events. A queued task or healthy heartbeat is not evidence
of a successful repair. Retain original action IDs and exact production receipts
for any resulting release.

Run `python3 -B test/check_platform_database.py` against its isolated loopback
PostgreSQL fixture. It executes the original control, lease, evidence, authority
and release checks, then the new trigger, backfill, daily-slot bypass, concurrent
deduplication, redaction, rollback, pause, cancellation and host-fencing checks.
Authentication, Storage and research transports in this fixture are synthetic.
It makes no production changes, provider calls, cloud launches or scientific
measurements. Actual autonomous coding, deployment and assessment resumption must
be verified separately in production.
