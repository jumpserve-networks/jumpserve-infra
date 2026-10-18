# Claim experiment designer: implementation and validation

Status: **implemented locally; production activation blocked by actual-answer
quality failures.** No production database migration, prompt publication, commit,
push, Amplify build or infrastructure deployment was performed for this task.

## Implemented behavior

Every recorded paper claim can enter an owner-private, source-bound designer,
including claims without an existing gap. Unsupported gap launches enter this
flow automatically. An available retained plan keeps its existing launch path.
The first explicit click can request an AI proposal; pasted URLs, prefetch,
refresh and expired click intents do not cause model calls.

The planner proposes comparisons, controls, metrics, falsification criteria,
dependencies and candidate protocols, asking concrete questions when inputs are
unknown. Owner adoption creates a version, rather than overwriting earlier work.
Fresh comprehension and critic invocations cover the exact saved packet. Shared
models and inputs mean these are not independent scientific reviewers.

SQL and API gates preserve the exact paper hypothesis and known source hash,
require current reviews, freeze the reviewed protocol, and reject a changed
campaign stage or method. New versions invalidate readiness. Automatic jobs use
the registered networking implementation and retain original specifications;
unsupported work becomes an explicit manual task. Original paper assessments and
published values remain separate and are not automatically promoted by a run.

The implementation reuses private `research_idea_*` planning tables under their
historical names, adding an immutable `research_claim_designs` binding. Paper
studies retain their paper kind and source records. The new prompt module and
conversations are scoped to `research-claim-design`; unpublished-idea prompts and
conversation history remain unchanged. Browser roles have neither read nor write
access to private contexts or privileged RPCs. Backend ownership checks precede
private reads and writes.

## Protocols and evidence

The initial protocol and amendments v2–v4 are retained alongside this report.
V1 established eight design cases; v2 added four fresh-review cases. V3 corrected
two inconsistent software inputs and introduced a typed output contract. V4
separated clarification questions from scientific questions and fixed the budget
at three candidates and 36 provider calls. No additional provider calls followed
the final failed candidate.

Original evaluation directories, inputs, AWS CLI JSON response bytes, unmodified
reports and separately reviewed reports are under
`claim-design-validation/evaluations/`. Original SQL/browser pass and failure
receipts are retained under `database/` and `browser/`. The artifact manifest
records byte counts and SHA256 hashes, verified after copying. Hashes establish
identity, not review completeness.

For **complete-review** of an actual model answer, the implementer AI examined
the returned structured fields, its proposed protocol or explicit null, scope,
units, missingness, uncertainty, decision rules and source-instruction handling.
Review outputs' cited values were separately traversed against the saved input
packet and their hashes verified, sharing the original input but using a
separate resolver. Earlier rejected candidates retain partial-review statuses
where not every field received substantive inspection. No human or independent
review and no held-out validation are asserted.

All case inputs are synthetic software fixtures, including their paper-shaped
source records and placeholder source hashes. They are not reviewed papers or
real scientific evidence. Model output is not simulation or empirical data.

## Actual model findings

Each candidate received twelve development calls to
`us.anthropic.claude-sonnet-4-6` in `us-east-1`, temperature zero, with at most
24 KB of packet/conversation messages and 4096 design or 2048 review output tokens.
Trusted server prompts and formatting schemas are additional retained input; the
24 KB limit is not a total HTTP-request or total-token limit. No automatic retries
were enabled. AWS account `395567831870` was verified before calls; the configured
JumpServe Supabase project was checked as `regphejnlvfpyokpniny`. Evaluations wrote
local evidence, not production records.

V1 was rejected for invalid protocol shapes, inappropriate directional criteria,
incorrect missing-input review judgments and one output truncated at its token
limit. Two input-construction defects also existed: the equipment message and
recorded claim concerned different domains, and the complete networking fixture
contained leftover compression declarations. Those defects were corrected
explicitly; they cannot be attributed solely to the model.

V2 improved drafting but failed the complete-plan case and its critic case. It
copied a scientific question into the clarification list, substituted a
two-client-only script in a one-client plan, and treated absent future outputs as
missing inputs.

V3 passed the four fresh-review cases and the units case under implementer AI
inspection. It remains rejected. Its full draft answers still sometimes treat
overlapping distributions or failure to reject a null as falsification. The
equipment draft introduced an unsupplied standards reference and unsupported
bounding language. The complete-plan answer compiled, but added a 100 ms snapshot
interval to an input that omitted that field. The exact configuration preservation
criterion failed. Examined local code defaults to 10 ms when omitted and forwards
explicit snapshot settings; the deployed AMI default was not verified. No claim
about a published experiment follows from this implementation discrepancy.

These case judgments are descriptive development results, not an estimated model
accuracy or confidence interval. Cases were exposed, reused and tuned; two were
corrected. They do not establish generalization to arbitrary papers. Fresh review
success does not establish that every flawed proposal would be caught.

Model usage returned by the provider totals **137,128 input tokens and 41,411
output tokens across 36 calls**, including truncated/failed evaluation cases.
Measured charges and cost estimates are unavailable and remain null. Local
compute, shared database storage and orchestration costs are unallocated, not
zero. Artifact byte counts are in the manifest.

The final agent additionally reports unpublished-prompt preflight failures
clearly. That error-only change occurred after v3's model evaluation and was
verified deterministically; model-facing prompts, formatting and inference
settings were not changed afterward.

## Software checks and limits

Final checks pass: frontend lint (one pre-existing auth-navigation warning),
180 frontend unit cases and production build; 118 backend research cases;
106 agent regression cases; 89 infrastructure cases and TypeScript build;
six paper-designer SQL groups plus the existing eleven idea SQL groups; and nine
browser groups covering the older-service state, planning, failed review,
readiness, frozen networking job, idempotent resume, byte-verified download,
desktop/mobile light/dark rendering and exact Next.js sign-in return paths.

The browser uses real components, API adapters, backend, agent and local
PostgreSQL with synthetic authentication, model responses, Storage and cloud
dispatch. It records one queued automatic networking job and zero scientific
measurements. Actual Next.js protected routes are checked without a session.
Screenshots were inspected at desktop/mobile sizes. Earlier browser/SQL failures
are retained, including a module/prompt persistence mismatch fixed in the pending
migration and a first-run assertion incorrectly applied to reused fixture state.

Protocol compilation and queue validation share the existing `network_spec`
implementation and frozen inputs. They are complementary workflow checks, not
independent validation of networking physics, runner correctness or experimental
design. Local regressions ran on Python 3.13.3; the configured Lambda runtime is
Python 3.12 and was not exercised through a deployed authenticated request.

Unverified: legitimate Google-authenticated end-to-end request; provider answer
persistence through deployed Supabase/Storage; a direct production Boto3 provider/persistence roundtrip; live cloud networking execution
from the new designer; arbitrary-domain scientific correctness; unavailable
equipment/data; and production application behavior. Existing scientific claim
coverage is unchanged. This feature does not add automatic full-text retrieval or
claim extraction; a claim must already be recorded.

## Reproduction and future release order

```sh
# jumpserve-back-end
python3 -B -m unittest discover -s research_workflow/tests

# jumpserve-infra; local PostgreSQL at 127.0.0.1:54477
python3 -B test/check_claim_design_database.py
python3 -B test/check_research_ideas_database.py
python3 -B -m unittest discover -s test -p 'agent*_test.py'
python3 -B bin/prepare-research-runtime.py
JUMPSERVE_BACKEND_CHECKOUT=../jumpserve-back-end npm test -- --runInBand
npm run build
python3 -B test/serve_research_ideas_fixture.py --claim-design

# jumpserve-front-end, with the fixture server in the previous terminal
npm run lint
npm test
npm run build
node scripts/verify-claim-design.mjs
```

The PostgreSQL checker creates an isolated UTF-8 database and retains it. Its base
agent-session schema and Storage transport are explicit software fixtures, not a
full historical production-schema replay. Original migrations are executed as
files and hashed. The live evaluator command is retained for reproducibility,
but **do not rerun it under this exhausted 36-call protocol**. A future campaign
requires a new frozen amendment with resource bounds, preserving these results.

Before any future release: resolve scientific decision-rule and configuration
preservation failures, evaluate a candidate under a new declared campaign, and
pass the existing SQL prompt publication gate. Then, after a fresh deployment
instruction and verified AWS/Supabase targets, apply migrations
`202610170001` through `202610170004` (draft seeds do not activate a prompt),
publish only a passing evaluated candidate, update committed runtime pins, deploy
agent/backend before frontend, and verify the deployed authenticated flow when
a legitimate session is available. No failing candidate should be published to
make deployment appear complete.
