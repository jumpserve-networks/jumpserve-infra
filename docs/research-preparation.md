# Source-grounded paper preparation

The intake path now connects an owning study to retained sources/claims,
configurations, frozen protocols, campaigns, claim links and stable queue jobs.
New intake defaults to preparing the exact registered paper plan. Existing
workspaces have **Prepare paper and queue checks**, progress counts and **Resume
queueing this plan** after a partial request. Creating a draft alone remains an
explicit option. Unknown papers need an uploaded researcher-prepared plan; this
release does not generate AI claims or conduct arbitrary domain experiments.

## What the IPv6 plan does

Exact PuRe item `item_3670144_1`, its reviewed PDF/resource aliases and DOI
`10.1145/3730567.3764439` identify registered `ipv6-archive-v1`. Matching a title,
different host or a later paper version never selects it. The manifest is
1,452,605 bytes, SHA256
`6bd31acb22a105c35ea9c54fa0a9381d0c5981bd554bed6443196b5eee3eebb3`.
Its generator pins the retained assessment bytes and regenerates this manifest
exactly; changes require a new version, with the old manifest preserved.

The plan imports 74 source records, 15 claims, 144 configurations, 15 prior
assessments and nine gaps. Six retrospective numerical campaigns recheck the
1,152 already-recorded means against separately transcribed published absolute
panel cells, under the exposed 0.0051 percentage-point tolerance. Fourteen manual
tasks prepare source/dependency reviews and full domain follow-ups for the other
claims. All 15 claims have applicable links; this is planning coverage, not
completed scientific validation. Queue completion does not alter claim labels.

The automatic checks share the earlier assessment's inputs and upstream errors.
They do not rerun raw packets/daily parsing, resolve discrepancies, reproduce the
relative figures, establish causality or measure today's Internet. The original
source access/review declarations, limitations and reviewer identities remain
visible. Imported SHA records do not mean that each literature PDF has been
copied to this new study's Storage. The original manifest and compiled plan are
retained privately; numerical workers retain their exact derived inputs/output.

## API and recovery

Google-authenticated owners use GET/POST
`/research/studies/{studyId}/prepare`. GET reports exact registered availability
and retained plan progress. POST has two strictly bounded shapes:

```json
{"action":"prepare","request_id":"UUID","plan_input":"optional exact original UTF-8 JSON"}
```

```json
{"action":"enqueue","prepared_id":"retained UUID","job_id":"planned UUID"}
```

Preparation validates the complete plan, uploads and retrieves/hash-verifies its
original/compiled bytes, then atomically appends the scientific records and
private metadata through `research_prepare_plan`. Enqueue reloads and verifies
the compiled artifact and selects that job's immutable request. Inputs, modes
and campaigns cannot be overridden in an enqueue request. Each enqueue is a
separate bounded API call; the client confirms study, campaign, mode and job
identity before increasing its saved count. Browser requests time out after 35
seconds, and already committed work remains available for recovery.

Study/manifest-qualified UUIDs prevent cross-study identifiers and duplicate
jobs. Concurrent preparation retains the first frozen protocols and records
additional verified compiled bytes as private attempt artifacts. Replay does
not refreeze or replace them. Failed, cancelled, reviewed and expired jobs are
already recorded jobs; resume never restarts them automatically. Existing
follow-up controls are required for another execution. Queue dependencies and
global/study/resource caps remain enforced by the existing scheduler.

`research_prepared_plans` is private and immutable, with RLS enabled and browser
SELECT/write/RPC access denied. Preparation creates neither publication nor
passed reviews. Scientific results retain the existing reviewed publication
boundary. Backend ownership checks apply to every preparation request.

## Preparing another domain

Upload original JSON <=250,000 bytes. Registered manifests have a separate
1,500,000-byte cap; compiled artifacts are <=4,000,000. No submitted code,
commands, model choice or credentials are interpreted. A manifest has exactly:

```text
schema_version: 1
plan_id: lowercase versioned name
title: descriptive plan name
paper_urls: exact aliases identifying one reviewed paper version
provenance: producer, source_version, prior_exposure, limitations
records: [{kind, record}, ...]
campaigns: [{key, campaign, protocol, claim_ids, execution_mode,
             raw_input, dependencies, priority, rationale, exclusive_resources}, ...]
```

Records use the existing `workflow.FIELDS`/`validate_record` schemas for sources,
claims, configurations, prior assessments and gaps. Inventory the main paper and
direct sources, actual access/review status and precise claim locations first.
Every claim needs a referenced source and at least one planned applicable link.
Plans contain 1–500 initial records and 1–100 campaigns. Each protocol must supply
all existing scientific design fields, including dependence, missingness, prior
exposure and resource/stopping rules. Source review declarations are retained
declarations, not certified independent review by the importer.

Campaign definitions use the existing frozen campaign schema without `id` or
`protocol_id`; those are bound during preparation. Claim IDs reference original
manifest claim records. Dependencies refer to campaign `key` and specify
`complete-run` or `reviewed-evidence`; cycles/unknown predecessors are rejected.
Automatic jobs currently support only `matched-numeric-v1` reanalysis or
independent numerical checks, <=1,000 observations and <=10 algorithm seconds.
Their `raw_input` contains published/observed arrays and is identified by an exact
original input hash in the protocol. Identifier rebinding preserves numeric
tokens, units and observation identities, and freezes the derived input hash.
Manual work has `raw_input: null`. It requires the domain operator, inputs and
any later main-experiment protocol; preparation never invents measurements.

Local dry-run from the backend repository, using fresh output paths and UUIDs:

```sh
python3 -B research_workflow/cli.py prepare-plan \
  --study-id STUDY_UUID --request-id REQUEST_UUID \
  --paper-url https://pure.mpg.de/pubman/item/item_3670144_1 \
  --output .test-artifacts/research-preparation/compiled-preview-v1.json
```

For an uploaded plan, add `--plan original-plan-v1.json`. Explicit `--persist`
requires the real owning `--actor-id`, a legitimate server-only credential and
the exact guarded JumpServe project. `--enqueue` additionally queues the retained
jobs and requires persistence. Persisted CLI output comes from the actual
first-retained compiled artifact, not a local preview with different timestamps.
Use the same plan to resume, choosing a new output filename to preserve history.

## Verification and release order

Protocol: [research-preparation-protocol-v1.md](research-preparation-protocol-v1.md).
These are exposed development checks, with AI implementer inspection; no human
or independent/held-out validation is asserted.

```sh
# Backend
python3 -B -m unittest discover -s research_workflow/tests -v
# Infrastructure: dedicated local PostgreSQL cluster at 127.0.0.1:54477
npm run test:research:queue
python3 -B bin/prepare-research-runtime.py
npm test -- --runInBand
npm run build
# Frontend
npm test
npm run lint
npm run build
npm run verify:research:preparation
npm run start -- -p 3004
npm run verify:research -- --intake
```

The component browser regression mounts the actual React component/helper with
a fixed synthetic transport. It checks interrupted/resumed requests, upload
errors and unknown-paper states, desktop/mobile themes. It cannot make external
requests and does not simulate a legitimate Google identity. Public guidance and
sign-in return paths are also checked in the actual Next.js app. An actual owner
browser request, remote Storage and deployed scheduling remain conditional.

No production mutation/deployment is included in this implementation turn. When
the current changes are explicitly authorized for deployment: verify account
395567831870/project regphejnlvfpyokpniny, then apply the migration before the
API/frontend. Keep the exact SQL and apply receipt.

```sh
python3 -B bin/research-workflow-database.py --apply-preparation \
  --output docs/research-preparation-validation/production-migration-v1.json
python3 -B bin/research-workflow-database.py --preparation \
  --output docs/research-preparation-validation/production-security-v1.json
```

Deploy the reviewed runtime manifest/API routes, preserving the existing worker
schedule, and then the frontend. Pin a committed backend revision before release;
the current manifest explicitly identifies its revision as the pre-change
baseline and pins the exact working-tree file hashes separately. Verify the
deployed capabilities/version, authenticated preparation of the reported existing
workspace, its 20 job definitions, numerical attempt history and private/public
boundaries. New studies do not migrate existing drafts automatically. The owner
can use **Prepare available checks and queue jobs** on the existing draft without
creating another study. Until deployment that control is not live.
