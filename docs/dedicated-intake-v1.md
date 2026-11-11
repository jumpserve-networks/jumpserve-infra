# Dedicated warm paper intake

This release prepares a separate AWS intake worker. It does not activate or
deploy itself. Ordinary interactive deployment still requires an explicit request
for these changes, as specified in AGENTS.md.

## Behavior

- A separate `t3.large` host runs one persistent, pinned OpenClaw Gateway with two
  inference slots. It has no inbound network rules. The Gateway listens only on
  loopback, with tools, plugins, browser use and model fallbacks disabled for this
  data-only worker. The experiment workers and development supervisor retain
  their existing capabilities.
- Four independent controller slots refill as work finishes. They lease at most
  two tasks per assessment, extract independent source chunks in parallel, and
  share the original assessment's funding and deadline. An idle controller backs
  off to 15 seconds; active controller work removes the one-minute Lambda wait.
- Organization includes the largest prefix of complete statements fitting both
  the actual 96,000-byte logical request and its provider wire representation,
  including policy, schema and prior shortlist. The old eight-item/12-KB limit
  remains compatible with the older general runtime until routing is activated.
- Each chunk uses the existing durable turn ledger and exact quote/page/offset
  checks. Chunk identities bind the source artifact and chunk hash. Completed
  siblings remain retained if another chunk fails. Only the root can finish paper
  preparation, and SQL rejects a premature root finish.
- Only source chunk zero supplies metadata. Paper scope confirmation and the
  existing scientific criteria remain intact. Full text extraction does not
  imply validation of omitted tables, figures or supplements.

The native Gateway receives a unique session and short hash-bound ticket per
turn. A loopback proxy sends its native request to the original per-turn bridge;
that bridge forwards the complete admitted request unchanged through the existing
one-inference gate. Tickets disappear after completion. Prompts, responses,
provider bytes, failures and provenance remain private versioned Supabase records
available through the existing bounded assessment projections. Child progress and
its turn history use existing Experiment Queue task records.

## Authentication and isolation

The original AWS host remains the sole OAuth refresh owner. A separate publisher
service on that host writes only the short-lived access value, expiry and health
metadata to SSM SecureString `/jumpserve/intake-access-v1` every 30 seconds. It
uses the original refresh lock and credential helper. No refresh grant is copied
to the new host or put into an asset, configuration or log.

The intake role can read that exact parameter and the existing private Supabase
service-key secret. An explicit deny prevents its SSM managed policy from reading
other parameters. The imported original role receives only the cache write and
exact publisher asset read grants. AWS credentials use instance roles. Cached
access older than 90 seconds, nearing expiry, or published by a paused owner
cannot admit new inference. Local quota and provider backoff observations persist
across process restarts; they do not reset provider allowance.

The original host's repair and installation drain rules exclude this separate
host's intake work. They retain their checks for original general research,
native supervisor runs, cancellation and uncertain external operations.

## Local qualification

`intake-worker-runtime.json` pins the backend revision and every runtime file.
The original `research-workflow-runtime.json` and original EC2 stack inputs are
unchanged. Prepare only declared files; mismatches stop staging and synthesis.

```sh
python3 -B bin/prepare-intake-runtime.py
python3 -B -m unittest discover -s ../jumpserve-back-end/research_workflow/tests
python3 -B test/check_dedicated_intake_database.py
python3 -B test/qualify_intake_native.py
python3 -B -m unittest discover -s test -p intake_release_test.py -v
npm test -- --runInBand test/intake-worker.test.ts
npm run build
npm run cdk:intake -- synth --quiet --output .test-artifacts/intake-cdk
```

The SQL suite creates an isolated local database, runs the preceding 133 controls,
then checks intake privacy, idempotent parallel admission, root readiness,
uncertainty, expiry, separate dispatch lanes, supervisor independence, rollback
and shared budgets. Native qualification uses the installed Node 24.16.0 and
OpenClaw 2026.10.5 fixture with synthetic upstream responses. It verifies two
concurrent native requests, reuse of the same Gateway process, exact provider
bytes and expired-ticket rejection. It makes zero external model calls.

These checks qualify software behavior. They do not measure production latency, independent scientific accuracy or a real provider-to-Supabase round trip.

## Release order after deployment is requested

1. Publish the exact backend feature revision before pushing the companion infra
   change, so CI can fetch the pinned intake source. Keep the general runtime pin
   unchanged. CI stages and tests intake separately.
2. Apply `database/202611050001_dedicated_intake.sql` to the correct production
   project, `regphejnlvfpyokpniny`. Routing starts disabled; existing intake stays
   with the original worker. Verify the migration in the normal audited release.
3. Deploy only the new stack, saving its resolved asset outputs:

   ```sh
   npm run cdk:intake -- deploy JumpServeIntakeStack --outputs-file .test-artifacts/intake-outputs.json
   ```

   Review its diff first. It adds separate encrypted compute and scoped policies
   on the imported owner role. It must not replace the original EC2 host.
4. Prepare and inspect the exact publisher request, then send it using the
   existing AWS deployment identity:

   ```sh
   python3 -B bin/prepare-intake-publisher.py --outputs .test-artifacts/intake-outputs.json --output .test-artifacts/intake-publisher-command.json
   aws ssm send-command --region us-east-1 --cli-input-json file://.test-artifacts/intake-publisher-command.json
   ```

   Retain and reconcile that command ID before any retry. The request verifies
   account, existing role, exact source binding and service hash. It installs
   only the access publisher beside the existing workers; it does not replace
   their runtime or native dependencies.
5. Read back both service states, the new host's exact source/native versions and
   the private `research_intake_runtime` heartbeat. Verify that its source binding
   equals the reviewed manifest, its Gateway is ready, and the publisher reports
   ready without printing the SecureString. Drain existing general intake leases
   and queued/running general intake dispatches before changing routing.
6. In an audited database-owner transaction holding the
   `research-autonomy-v1` advisory lock, recheck the fresh ready heartbeat, exact
   source binding and original-worker drain, then set
   `research_intake_runtime.enabled=true`. Heartbeats and service-role table
   updates cannot activate this flag themselves.
7. Submit a real paper through the normal owner flow. Verify parallel source-bound
   child turns, exact quotes/pages, original Supabase artifacts, complete chunk
   accounting and final grouping. Measure submit-to-first-claim,
   extraction/grouping wall time, queue wait, model calls and failures. Compare
   against the retained baseline without claiming synthetic timings as live
   improvement. Preserve the assessment's uncertainty and coverage limits.

## Restart and rollback

The publisher can also be installed through the protected
`intake-publisher-release.yml` workflow using the existing
`JumpServePlatformRelease` GitHub OIDC role. It accepts only a release UUID,
the exact protected source revision and the deployed content-addressed runtime
and publisher objects. It validates inputs before role acquisition and invokes
the same pinned publisher request on the original refresh owner. A private S3
intent is written before sending SSM, client mutation retries are disabled, and
a lost acknowledgement is reconciled by its original release UUID. An
unconfirmed intent cannot send another command. This path uses no desktop AWS
session or copied long-lived credentials.

The intake stack also grants this protected role SSM maintenance and console
read access to its exact intake host, plus the metadata reads needed to resolve
and verify that host. `intake-bootstrap-diagnostics.yml` uses fresh OIDC sessions
and checks the stack's source binding before collecting service/bootstrap state.
It accepts no host IDs, shell commands or static integration keys from callers.
Bootstrap checks import the pinned package as the service account, after making
only immutable code directories readable/traversable. Private auth/state paths
retain their restrictive permissions.

Completed captured answers can resume controller work without another inference.
An expired uncertain provider invocation remains blocked under its original ID;
new child IDs cannot replace it. The durable completion outbox retries storage
only. Cancellation stops admission, while already captured outcomes remain
recordable. Task leases are 420 seconds; the dedicated completion wait is bounded
to 330 seconds and dispatch leases to 235 seconds, within the original assessment
deadline. Native per-call time and request limits remain unchanged.

For rollback, disable routing to stop new leases/claims, let current outcomes and
outbox writes drain, then stop the intake service and its access publisher. Do not
copy refresh grants or delete assessment evidence. Warm-owned roots and children
remain paused for the qualified intake runtime, rather than being handed to an
older worker that cannot interpret parallel state. Unstarted legacy roots remain
compatible. Keep the original EC2 services and runtime pin unchanged. Re-enable
only after verified source/readiness checks; never reset limits or replay unknown
calls to obtain a successful result.
