# Claim plan reuse production release v1

Released 2026-10-18 UTC under the user's explicit instruction to merge all current
work to main and deploy. All three repositories were already on main, so no
separate branch merge was necessary. Earlier protocols, failed model evaluations,
the failed production adoption attempt and its checkpoint remain unchanged.

## Production status

Backend main 2a394ce1cc6597603f78a6a3853a8327e10bae43 is deployed through runtime
manifest version 16. Infrastructure release commit
43215cbd97a5c897027306264dd47c061e5fa80c pins all sixteen runtime file hashes.
Frontend main 6a501dc52db02b2caf248722690f6a4feaea2575 was released by automatic
Amplify build 115, which succeeded at 2026-10-18T03:45:04.838Z.

Verified targets: AWS 395567831870/us-east-1, Supabase regphejnlvfpyokpniny and
https://jumpserve.quaint-lab.org. Migration 202610180001 adds a backend-only,
owner-checked audited reuse operation; RLS and browser write denial are retained.
The scoped API stack deployment completed successfully and retrieved Lambda ZIP
hashes match the committed runtime. The reviewed diff changes code for five
existing functions, with no route, IAM or resource replacement changes. Original
before/after archives are retained separately. Agent and published prompts are
unchanged; the active claim prompt remains research-claim-design-v6.

## Authenticated verification

The original adoption request dd1184e9-9b2e-4e0c-93eb-06923d63a3a3 failed with
HTTP 503 before the correction. Retrying that same request after deployment
returned HTTP 200, packet 15e898f0-4f21-454b-86ae-b6399526ae76, version 3 and SHA256
66a242eded9f15863f2b2dee16c9f8c443805e6937998464da24eb54fdc151d9. The response
explicitly records new_packet_created=false and review_budget_preserved=true.
There are still three packets, rather than an identical fourth version.

After the frontend release, the real Google-authenticated browser displayed
"Use this saved plan". Clicking it again returned HTTP 200 and the correct
unchanged-version message. Both uses are audited; neither creates readiness or
resets the retained model history. The original failure remains visible in the
private operation evidence. No tokens, cookies or authorization headers were
exported.

Two earlier actual planning calls and one exact 399-byte owner configuration
upload/retrieval passed. Configuration SHA256 is
a0c00449a809ff1e67c2b3e3ef48e4eacaa6652f67bd65ab6bbdbe46b948188a; independent
read-only retrieval matches the browser's original bytes, and anonymous read is
denied. Retrieval verifies bytes, not substantive source review.

Fresh actual comprehension run 20ac65a7-002d-49df-aa3b-89d9462c7f7b returned ready
with warnings. Fresh critic run 6d7e9741-0d8f-4d31-baa4-6c0c92f172f0 returned
needs-clarification with a blocking required-input finding in conditions, inputs
and configurations. It asks which required inputs are available and how missing
inputs will be resolved. The readiness and freeze buttons remain disabled.
These are actual AI judgments, not human or independent scientific reviews. The
critic's generic question does not identify a demonstrated missing-input mechanism
or establish scientific invalidity. We retained the finding and stopped without
inventing availability, overriding the gate or tuning away the failed review.

Actual experiment execution remains unverified. There is no readiness record,
frozen campaign, queue job, experiment run, measurement or new scientific
assessment in this private pilot, and no experiment VM was launched. The single
condition acquisition pilot cannot resolve the paper's BBRv1 sensitivity claim.
The original public study's entire record sets compare equal to their retained
pre-verification snapshot, including eight assessments and 36 measurements.

## Checks and evidence

Release checks pass: 123 backend tests, 180 frontend tests, 89 infrastructure
tests, frontend lint/build, infrastructure build, seven claim SQL groups, eleven
existing idea SQL groups and eleven integrated local browser groups. The existing
auth-button internal-navigation lint warning remains. Local auth, model, Storage
and cloud responses are fixtures and are labeled accordingly.

Five deployed public browser groups pass: source-bound design links and exact
sign-in return paths; private-route/malformed-ID boundaries; desktop and mobile
(1365 and 390 pixels), light and dark themes with no horizontal overflow; exports
and missing-study states; landing, results and methods navigation. Anonymous
private/model API requests are denied. The separate authenticated checks above
use the user's legitimate production session and persisted actual answers.

Original producer receipts, logs, SQL/browser reports, screenshots and per-file
hashes are in [the evidence manifest](claim-packet-reuse-release-evidence-v1/artifact-manifest.json).
Machine-readable release and operational outcomes are in
[release-summary.json](claim-packet-reuse-release-evidence-v1/release-summary.json).
The new evidence archive is private in Supabase; its storage receipt is recorded
separately after upload and hash-verified retrieval. It excludes session material
and private user history. Model requests, original response representations,
packet versions, configuration bytes and both review outcomes remain in the
existing private Supabase relations/Storage.

Reproduction entry points (local services and declared fixture setup required):

```sh
# jumpserve-back-end
python3 -B -m unittest discover -s research_workflow/tests
# jumpserve-infra; isolated PostgreSQL on 127.0.0.1:54477
npm test -- --runInBand
npm run build
python3 -B test/check_claim_design_database.py
python3 -B test/check_research_ideas_database.py
python3 -B test/serve_research_ideas_fixture.py --claim-design
# jumpserve-front-end
npm test
npm run lint
npm run build
node scripts/verify-claim-design.mjs
node scripts/verify-claim-design-production.mjs
# jumpserve-infra; fixed-target read-only production inspection
python3 -B bin/claim-design-release.py verify
python3 -B bin/verify-authenticated-claim-flow.py observe
```

Model usage across the authenticated campaign: four successful calls, 25,051
input and 751 output tokens (25,802 total); no automatic retry and no hidden
replacement calls. Measured charges, model cost estimates and unallocated
orchestration/storage charges are missing, not zero. No experiment compute was
requested. Release deployment/build resources are not included in model usage.

Software deployment and the unchanged-plan correction are verified. Remaining
conditional gaps are reviewed-input resolution followed by actual authenticated
readiness/freezing/queue execution/acquisition/termination, another legitimate
user's isolation, real-world and custom-package runners. Custom-package admission
remains disabled. No scientific claim label is changed. Evaluator and operational
reviewer: primary Codex AI implementer, non-independent; no human review claimed.
