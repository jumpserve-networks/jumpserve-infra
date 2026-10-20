# Implementing and reproducing bounded autonomous follow-ups

This is a local, uncommitted candidate. See the validation report before using
any release commands. Candidate v8 is unpublished and its completion evaluation
failed; **do not deploy or publish it with a bypass**. No production deployment
was requested for this implementation turn.

## Code and provenance

Backend: `research_workflow/autonomy.py`, `autonomy_model.py`,
`autonomy_evidence.py`, `autonomy_costs.py`, `bounded_network.py`,
`network_execution.py`, `network_spec.py`, `store.py` and
`policies/autonomy-experiment-costs-v2.json`. The runtime manifest is version 25
with 25 exact file hashes. Its `source_revision` is the previous clean base,
with `revision_status` explicitly identifying the uncommitted candidate. It
does not pretend that the old commit includes this work. Both live candidate
profiles retain original runtime copies; v8 test helpers are retained too.
The v7 producer's complete historical helper state was not frozen before a
later test-helper edit; frozen requests and all runtime bytes remain available.

Frontend accepts both autonomy API versions, shows check-coverage counts in the
queue and adds numeric bounded-TCP controls to the networking protocol editor.
Infrastructure defines a dedicated immutable Lambda, narrow worker permissions
and a held rollout flag that provisions the runtime while keeping API autonomy
admission and polling disabled. SQL migrations `202610190001` through `008` are
additive and retain failed prompt drafts and earlier publication requirements.
No new browser write grants or public artifact permissions are introduced.

Do not rerun the old candidate preparation scripts against current bytes:
`prepare-autonomy-followup-candidate.py` generated the original v7 profile and
`prepare-autonomy-v8-candidate.py` generated v8. Their output is retained history,
not a command for overwriting the original campaigns.

## Local verification commands

From `jumpserve-back-end`:

```sh
python3 -B -m unittest discover -s research_workflow/tests -v
```

From `jumpserve-front-end`:

```sh
npm test
npm run lint
npm run build
```

From `jumpserve-infra`:

```sh
npm run build
env JUMPSERVE_BACKEND_CHECKOUT=/Users/Shared/allstar/jumpserve-back-end npm test -- --runInBand
npm run test:research:autonomy
```

Database checks require a disposable local Postgres server on 127.0.0.1:54477,
role `michael`, and the repository fixture bootstrap. They create unique test
databases. They do not target Supabase. Tests synthesize the legacy `agent_sessions`
base table and run the listed original research/prompt migrations; unrelated
historical study-table migrations are outside this bootstrap.

For the browser campaign, start the fixture using
`npm run test:research:autonomy:browser-fixture` in infra, and a fresh frontend
production build with `npm start -- --port 6002`. Run
`npm run verify:research:autonomy` in the frontend. The verifier binds its own
fixture page, uses actual components and styles, and checks real Next anonymous
redirects separately. Google/provider/source/Storage are explicit fixtures.
An existing user dev server can be stale after changes to Next redirect config;
do not kill it to make a check pass. Stop only processes started for this campaign.

Live model producer commands are retained for audit, **not automatic replay**:

```sh
python3 -B test/evaluate_autonomy_followups.py --prepare --campaign v1
python3 -B test/evaluate_autonomy_followups.py --live --campaign v1
python3 -B test/evaluate_autonomy_followups.py --prepare --campaign v2
python3 -B test/evaluate_autonomy_followups.py --live --campaign v2
python3 -B test/evaluate_autonomy_followup_completion.py --prepare
python3 -B test/evaluate_autonomy_followup_completion.py --live
python3 -B test/evaluate_autonomy_followup_completion_v2.py --prepare
python3 -B test/evaluate_autonomy_followup_completion_v2.py --live
```

Those destinations are immutable/already attempted. A future experiment needs a
new versioned protocol/directory, retained original criteria and a new resource
allowance. Do not rerun failed/uncertain provider calls. Every read uses an
attempt; reader/tool safety does not guarantee that a model converges before
the application's 25-attempt limit.

After actual answer inspection, `bin/review-autonomy-followups.py
--record-ai-review` writes separate reviewed reports once; it preserves producer
reports and identifies primary AI review. `bin/autonomy-followup-release.py
--mode check` archives local evidence and then fails closed on the unsuccessful
completion evaluation. This expected release-gate failure is retained and is
distinct from the passing unit/SQL/browser checks. It makes no cloud requests.

## Future rollout, after a passing candidate and an explicit release request

1. Fix and evaluate the remaining completion behavior under a new predeclared
   protocol. Retain current failures. Update publication guards to the exact
   passing candidate and evidence; do not weaken or remove the failed criterion
   to claim an original pass.
2. Commit the exact backend changes and pin its clean commit in the runtime
   manifest. Keep runtime file hashes equal to the evaluated profile; changes to
   those bytes require new evaluation. The deployment helper denies a dirty or
   incorrectly pinned backend. Preserve this local manifest/report as history
   when creating a separately versioned release profile.
3. Deploy the backward compatible frontend before activating a v2 backend.
   Verify AWS account **395567831870** and Supabase **regphejnlvfpyokpniny** before
   every cloud/database mutation. The connected unrelated Supabase project is
   unsuitable for these operations.
4. Hold old autonomy API admission and polling using the established fixed-target
   hold mechanism. Wait at least 70 seconds after the API hold; drain running
   tasks and turns. A guard requires these conditions before prompt publication.
5. Apply additive migrations and publish only the passing prompt, then deploy the
   pinned runtime with `researchAutonomyAdmissionEnabled=false`. The new fixed-target
   helper has `migrate`, `publish`, `deploy`, `verify` and `activate` modes. All
   require passing reviewed completion evidence; none was executed here. The
   older v6 publication/deployment helper does not represent this candidate.
6. Before publication, the new helper uploads an immutable content-addressed ZIP
   of all current successful/failed research evidence to private
   `research-workflow-raw`, retrieves it, verifies bytes/hash and denies anonymous
   retrieval. Model publication metadata links that archive. Credentials never
   enter the archive, command output or client bundle. Local-only inventory and
   remote retrieval status remain distinct. Future release archives may differ
   when clean commit metadata is pinned; preserve the local inventory.
7. Verify deployed original ZIP hashes, all three research function source hashes,
   the qualified bounded function source/configuration, logs-only permissions,
   no EC2 resources and unchanged private relations. Exercise an authorized real
   cloud loopback job, check its original/parsed artifact retrieval and exact
   configuration identity, and verify timeout/unknown-dispatch cleanup behavior.
   The current `verify` mode checks source/resource identity but does not replace
   the authenticated execution/Storage checks.
8. Activate admission/polling only after required checks pass. Verify the deployed
   queue and prompt history from a legitimate owner session, desktop/mobile and
   unavailable-data states. Do not reset old paper budgets, attempts or deadlines;
   expired work remains stopped. Recovery applies only to the known safe
   pre-dispatch size failures and retains prior reviews.

This rollout does not approve autonomous EC2, external-CDN or arbitrary package
spending. Those runners require their own verified resource lifetimes,
termination/lease controls, qualified implementation and dated cost envelopes.
