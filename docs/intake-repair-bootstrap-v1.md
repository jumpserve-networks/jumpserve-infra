# Intake initialization and supervisor source delivery repair

Status: prepared and tested locally; not published or installed in production.
The assessment remains blocked until deployment and a verified resume.

## Prepared changes

The dedicated intake lease adds `intake_pool_version` before the first controller
turn. The old `if not context` initialization guard therefore skips source
registration and reads a missing `text_artifact_id`. The isolated runtime repair
treats only an empty context or the exact warm routing marker as fresh state.
It retains that marker when registering the source. Partial work is never reset.

Runtime branch `fix/intake-initialization-runtime-20261105` is based on the actual
deployed source `e1dcb31b2f02a92118f2505e4e20b9f4a9181cf5`. Its local commit is
`3f08f2115a68e1e14fa5cd9616599d2ec589d23b`. Only two executable lines and a new
regression file differ. Later API and author changes on backend main remain
outside this dedicated runtime packet. Publish this reviewed branch through
protected main before referring to its exact source revision from an infra pin.

The supervisor branch `fix/intake-repair-bootstrap-20261105` adds passive runtime
source delivery to its existing `originals()` stage. It verifies actual local
supervisor modules and broker files against the activation manifest, delivers
those bytes separately from repository references, and supplies predecessor
tests at the revision whose supervisor bytes were observed. Scoped owning
infrastructure source is pinned at its current main revision. A changed reference
is new diagnostic evidence; an old blocked report is retained before reopening
one coding opportunity. Unchanged evidence does not clear another blocker.
Candidate references are never loaded as the installed qualification broker.

This repairs the missing source inputs. It does not certify that every requested
capability has been implemented or that self-repair is universally autonomous.
Do not mark the old capability dependency chain complete without activation
evidence. Once the assessment resumes, record its actual incident outcome and
retain or explicitly supersede obsolete requests without rewriting history.

## Local qualification

- The new regression reproduces the original `KeyError` and passes with the fix.
- Exact intake predecessor: 529 research tests, no skips, including the pinned
  native runtime and synthetic auth checks. No real provider call is made.
- Supervisor: 130 tests, including installed/reference separation, missing and
  altered files, links, predecessor identity, and unchanged-blocker behavior.
- Isolated Postgres: 146 checks, including six recovery checks. Original limits,
  counters and context remain unchanged. Unknown calls, partial contexts, owner
  pause, wrong/stale source and an expired deadline cannot resume.
- Narrow AST qualification admits only the exact two initialization edits while
  freezing other runtime bytes, scientific criteria and existing tests.
- Installer tests exercise real local file swaps, original-source retention,
  rollback, drain refusal, policy tampering and added executable rejection.
- Intake CDK test and TypeScript build pass. The added S3 read grant covers only
  the stable repair-object prefix. Source updates use content-addressed objects
  and independent old/new file verification without requiring another IAM grant.

Retained packets are local ignored artifacts:

```text
.test-artifacts/intake-initialization-repair-v2/packet.json
.test-artifacts/intake-initialization-repair-v2/bundle.zip
.test-artifacts/intake-initialization-repair-v2/resume-after-verified-install.sql
.test-artifacts/intake-initialization-install-final.json
```

The packet's source binding is derived from every declared runtime file. It is
not a production installation certificate. `prepare-intake-initialization-*.py`
only qualify source and prepare files; they never upload, send SSM or execute SQL.

## Deployment after an explicit request

1. Publish reviewed backend and infra changes through required protected checks.
   Install the supervisor source-delivery update through its existing qualified
   self-update route, retaining the original operation/SSM identity. Verify its
   actual installed source and the delivered reference index.
2. Disable intake routing under the `research-autonomy-v1` advisory lock. Let
   original leases, dispatches and completion writes drain. Preserve unknown
   provider calls and every private spool/availability record.
3. Stage the packet's exact backend revision. Use its prepared
   `intake-worker-runtime.json` as the reviewed intake pin, then review/deploy only
   `JumpServeIntakeStack`. The role's S3 read grant must include the prepared
   `intake-repair/*` prefix. Reconcile the stack update before
   sending an install command; the host's routing remains disabled.
4. Prepare the installation request against saved stack outputs with
   `bin/prepare-intake-initialization-install.py`. Upload exactly its four
   hash-indexed files with immutable S3 writes. Before sending SSM, reconcile any
   existing command carrying its release UUID and exact parameters. Disable
   mutation retries; retain the first command ID and inspect that outcome.
5. The installer independently checks routing/drain, old host source, every new
   byte and the exact AST fix. It imports the staged code as `jumpserve`, retains
   the old directory, swaps only the dedicated intake code, and restarts only
   that service. A failed service start restores the original pointer. It never
   enables routing or edits authentication, quotas, evidence or assessment state.
6. Verify the SSM outcome and actual installed files. Wait for a fresh `ready`
   heartbeat with the new binding, pinned native version and verified Gateway.
   Execute the owner-only prepared resume transaction for assessment
   `e2f224a3-9ad5-4cc2-9249-7792c32f294d`. It accepts only the exact fresh zero-call
   failure, preserves original limits, adds an audit event, returns the review to
   `preparing` and enables intake. It cannot confirm scope or alter findings.
7. Verify real source initialization, extraction dispatch/result persistence,
   complete source-chunk accounting, organization, and public `ready` status.
   Retain actual timings and remaining blockers. Do not infer live parallel
   throughput or unattended completion from local fixture results.

Rollback keeps routing disabled until the original source and service have been
verified. A lost response is reconciled under the original command identity;
neither another install nor another provider call is an uncertainty workaround.
