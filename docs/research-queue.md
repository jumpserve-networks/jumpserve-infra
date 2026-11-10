# Claim queues and bounded parallel evaluation

Queue capacity and prerequisites are enforced by PostgreSQL. Hosting concurrency is a separate deployment setting; inspect the current infrastructure configuration before release.

This extends the [research workflow](research-workflow.md). Claims track conclusions; campaigns execute checks. An applicable claim-check mapping is required before queueing. Several claims can share one job, and one claim can need several campaigns. Shared data, code, controls or reviewers are never counted as independent replication.

## Owner workflow

The Google-authenticated study workspace includes a private claim queue. Add
sourced claims, applicable campaign mappings and frozen protocols first. Submit
a campaign with its original UTF-8 input, priority (1 highest, 5 lowest), rationale,
exclusive resource names, optional follow-up predecessor and typed prerequisites.
Prerequisites refer only to earlier jobs in the same study; immutable definitions
prevent cycles and silent changes after execution. New conditions or retries use
new IDs and follow-up reasons. Jobs and events have complete private JSON exports.

- `complete-run`: a predecessor has a complete recorded run. A numerical
  discrepancy can meet this execution criterion; partial coverage cannot.
- `reviewed-evidence`: every applicable claim linked to the predecessor campaign
  has an explicitly accepted assessment citing its run and campaign. An
  inconclusive/discrepant assessment is allowed; this milestone asserts reviewed
  evidence, not reproduced claims or independent review. Assessments retain their
  actual human/AI identity, independence, conditions and limitations. Later
  assessments do not rewrite this historical acceptance event.
- Manual tasks: source review, proofs, standards, author/domain implementations,
  interventions and equipment-dependent measurements remain explicit. Import
  original domain run evidence through the existing trusted importer and attach
  its run from the same campaign when prerequisites are satisfied. The queue does
  not verify that external execution followed the prerequisite order; the
  recorded dates and protocol require substantive review.

Review evidence through the existing assessment editor, using
`[{"kind":"runs","id":"FULL_RUN_UUID"}]` evidence references and the exact
campaign ID. The queue action requires an assessment for every applicable linked
claim. No runner or scheduler automatically changes a scientific label.

Public results retain reviewed scientific snapshots and run provenance. Operational
queue state, raw input references, events and actor identities stay private.
The public methods page includes an explicitly synthetic teaching example of the
same display component, including mixed, empty and unavailable states. It is not
an authenticated owner session or scientific evidence.

## Execution and resources

Scheduled workers poll every minute. Each invocation starts at most two job slots;
two reserved Lambda invocations bound hosting concurrency. Short PostgreSQL
transactions atomically cap global running jobs at four and study jobs at two,
and prevent overlap of declared exclusive resource names across studies. Computation
runs outside the transaction. Priority order applies among eligible jobs, not
jobs awaiting dependencies/resources. Continuous high-priority arrivals can delay
lower-priority work; fair-share scheduling is not asserted.

Only `matched-numeric-v1` reanalysis/independent arithmetic runs automatically:
256 KB exact original inputs, 1,000 observations, 10-second algorithm bound. The
worker Lambda has 512 MB configured memory and a 180-second hosting deadline;
leases last 600 seconds. Two threads can overlap I/O; they do not imply independent
CPU cores, samples, implementations or reviewers. Statistical dependence, multiple
testing, stopping rules and inference remain part of each frozen scientific
protocol; this adapter reports descriptive comparisons only.

Original input/output bytes are privately stored and hash-verified after retrieval.
Evidence append and job completion are one fenced transaction. Queue definitions
and events are immutable; operational status changes are audited. Complete/partial
runs await assessment; failed/cancelled/expired attempts retain reasons. Expired
leases refuse late completions and never rerun an experiment automatically.
Unstarted jobs may be cancelled; running jobs cannot be cancelled through this
bounded numerical interface. No arbitrary submitted code, network probes, model
calls or experiment instances are launched. Undeclared resource contention remains
a limitation; manual/external execution is outside the worker slot accounting.

If computation or output persistence fails before evidence can be atomically
recorded, the job records a failure and preserves its already stored input. A
transport timeout can leave completion unconfirmed until lease expiry. Retain
operator evidence and investigate before creating a follow-up; no exactly-once
external side-effect guarantee is asserted. Available algorithm/worker wall time,
input bytes and configured hosting memory are recorded. Charges/model usage and
peak memory stay missing when unavailable; missing cost is not zero.

## Commands and checks

From backend:

```sh
python3 -B -m unittest discover -s research_workflow/tests -v
# Trusted server operator only, with existing server-only Supabase configuration:
python3 -B research_workflow/worker.py
```

The latter is a single bounded poll, not a daemon or browser action. It uses the
guarded JumpServe project/secret configuration. Do not run against production
without the current deployment authorization and release checks.

From infrastructure, with the dedicated local cluster on port 54477:

```sh
npm run test:research:queue
python3 -B bin/prepare-research-runtime.py
npm run build
npm test -- --runInBand
```

The queue database test creates a fresh `jumpserve_research_queue_test_TIMESTAMP`
database on loopback. It preserves failures, databases and original fixture bytes
under `.test-artifacts/research-queue/TIMESTAMP/`. Local Storage transport is a
byte-preserving fixture, not remote Supabase validation. Eight concurrent clients
exercise actual database RPCs; actual worker code records a discrepant numerical
run and dependency/review decisions. Backend barrier tests exercise overlapping
worker slots. All cases are development regressions, not held-out validation.

Frontend checks use `npm test`, `npm run lint`, `npm run build` and
`npm run verify:research:public-queue`. The browser verifier uses synthetic
backend records for the current assessment and queue pages.
Actual authenticated queue creation, review actions, Google login, remote Storage
and deployed scheduled invocation remain conditional checks when credentials and
a legitimate session are available.

## Release order: new explicit deployment request required

1. Pass local checks on the exact release bytes and prepare the runtime manifest.
2. Verify the intended AWS account and Supabase project. Apply the current
   workflow and queue migrations with a new receipt:

   ```sh
   python3 -B bin/research-workflow-database.py --apply-queue \
     --output .test-artifacts/research-queue/database-apply-v1.json
   ```

   `--queue` verifies all twenty relations and the queue RPC browser denial
   without applying changes. Existing schema replacement is refused. Catalog
   checks do not recover the originally executed migration bytes.
3. Prepare exact backend runtime bytes and release the benchmark API with
   `researchWorkflowEnabled=true`; queue scheduling additionally requires the
   explicit `researchQueueEnabled=true` context flag. Scheduling defaults off.
   The API reports worker activation so ready jobs do not falsely imply execution.
   Worker IAM is log permissions plus the existing service-key secret read; no
   EC2/Bedrock or arbitrary execution permissions are granted.
4. Exercise legitimate owner enqueue/review/cancel/cross-owner-denial requests,
   remote original-byte round trips, a scheduled two-job run and expired lease
   recovery. Record conditional gaps precisely. Publish frontend after API/schema;
   never deploy a build containing the local fixture origin.
5. Verify deployed public results, owner queue, desktop/mobile, themes, exports and
   sign-in return paths. Recheck evidence hashes and record measured/estimated/
   unallocated usage separately. Software readiness is distinct from scientific
   coverage. Queue activation alone resolves no claim.

Rollback disables scheduling by an authorized infrastructure release. Preserve
the queue, events, original artifacts and scientific evidence; do not drop data.
