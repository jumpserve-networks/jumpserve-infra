# Operational incident closure and original working checkpoints

The supervisor can be healthy while repeatedly investigating an incident that
the assessment controller already repaired. This change separates operational
closure from a qualified platform change and supplies the original working
checkpoint that an offline coding sandbox previously could not read.

## Retained reproduction

Task `3ed262aa-e62f-4bed-9e35-d0be66c37150` repeatedly requested the original
checkpoint named by `rebase-conflicts.json`. Its reference was a private Supabase
storage pointer. The archive was available and hash-correct, but no local file
was delivered to the network-free coding sandbox. The retained original has
SHA256 `3b655f6a068c9add6af6d245d37df4b01226016f76ff5fcfd875bf03923f492b`
and 3,363 bytes. Its controller plan has SHA256
`2e5074f011e5dfbadb2da4e89cad6a90d23687efd3582393a08fa099e8081f30`.
The failed task eventually reached its original deadline; this change does not
extend that deadline or rewrite its terminal outcome.

Meanwhile, ordinary successful planning turns changed the incident evidence
revision. The existing monitor could reopen the linked supervisor task even
after its exact assessment repair was resolved. Reopening a task did not produce
a qualified code change.

## Checkpoint delivery

`platform_supervisor/working_evidence.py` uses workspace reports only as
untrusted selectors. It requires a task-scoped server artifact named
`repair-source-refresh-plan.json`, checks the plan hash and current source
revision, then resolves the original `working-checkpoint.zip` through another
task-scoped server artifact. Paths, metadata, sizes, hashes, archive members,
duplicates, links, and expansion limits are checked before delivery.

The exact original ZIP is copied under `references/working-checkpoints/`, with
a passive member index and a local reference in the report. Nothing is extracted
into candidate source or executed. Original pointer, conflicts, proposed
deletions, source snapshots, and publication safeguards remain intact. Local
copies are reconstructed on later turns from the same originals.

The database advertises the versioned delivery contract. A previously blocked
task with a retained controller plan can receive one capability handoff within
its original authorization, deadline, cancellation, and uncertainty guards.
The worker must verify the actual original bytes before admitting another coding
call. A trusted, monotonic set of delivered plan/original hashes prevents deleting
or rewriting local reports from creating another evidence version or resetting
the no-progress guard. Missing or modified originals remain honest blockers.

## Operational closure

Migration `202611010011_platform_incident_closure.sql` derives closure entirely
from server records. It requires the exact linked repair/dispatch/task identity,
a terminal resolved repair with validated evidence and its matching immutable
event, and a completed subsequent controller turn with matching request and
retained response-artifact identities. A failed incident dispatch must be
accounted for by the existing trusted reconciliation adapter. Current unknown or
running research calls, new active repairs, blocked assessment tasks, stopped
workflows, and insufficient evidence prevent closure.

Closures are immutable private records. Settled linked supervisor tasks can stop
with an explicit no-change outcome, and resolved outbox records do not create
replacement investigations. An active worker stops only at its validated lease
boundary. A dedicated checkpoint path requires that exact server closure,
quiescence, no changes or releases, and the original owner controls. It preserves
the normal research admission cooldown. Ordinary completion still requires
recorded production verification; no source-change completion can use this path.

The migration leaves original assessment rows, scientific labels and criteria,
terminal repair/model outcomes, commitments, category limits, deadlines, and
uncertain calls unchanged. Expired or cancelled supervisor tasks are not converted
to successful repairs. Closure claims neither an autonomous deployment nor a
scientific finding.

## Verification and release

```sh
# jumpserve-back-end
python3 -B -m unittest discover -s platform_supervisor/tests -q

# jumpserve-infra, isolated loopback PostgreSQL fixture
python3 -B test/check_incident_closure_database.py
python3 -B test/check_working_checkpoint_retained.py
```

The PostgreSQL suite runs all 84 predecessor controls before new migration,
concurrent closure, refusal, live-lease, immutable-history, owner-control, deadline,
outbox, and one-time delivery checks. The retained control uses ignored private
original bytes and verifies the real failed handoff without production mutations,
provider calls, or execution of archived code. These are implementing-AI software
checks, not independent scientific or unattended-completion qualification.

The first production passive probe caught a persistence-adapter integration
failure: the bounded `limit=2` metadata lookup collided with `Store.rows`' default
limit. That failed probe remains recorded. The corrective worker accepts an
explicit query limit while preserving the task selector and the default bound.
Three additional regressions exercise the actual production adapter, including
the original-metadata plus storage-GET path; they do not replace the existing
delivery controls. The correction must pass its source-bound qualification and
the same real production probe before delivery is described as verified.

Production remains unchanged until an explicit deployment request. A release must
qualify the exact supervisor bundle, apply the forward migration under the existing
bounded maintenance procedure, install and hash-verify the new worker, and restore
the original admission settings. The assessment runtime and immutable experiment
executor do not need new code or a new pin for this change.

After release, verify an actual local checkpoint delivery and immutable closure
receipt, no extra coding admission for the resolved incident, normal research
continuation, and unchanged uncertain calls. Preserve all original failed and
expired task records; do not manufacture a passing autonomous release metric.
