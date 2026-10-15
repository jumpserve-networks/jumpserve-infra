# Source-faithful idea reviews

The original failed critic identified an invalid bootstrap procedure but described
the statistics field as containing the opposite declaration. The correction
separates recorded facts from model judgments.

Fresh comprehension/critic calls use a bounded classification channel: issue code,
warning/blocking severity, and references from the allowed packet-field inventory.
The model cannot supply source prose, quotes, values, summaries or a readiness
verdict. The backend checks each reference, copies the exact recorded value and
derives the displayed questions/findings/readiness from the issue classifications.
Unrecognized references or extra prose are retained as invalid output. No repair,
automatic retry or model-requested action occurs. Ordinary planning and the
idea-specific interview retain separate task templates.

The interface exposes recorded declarations in both guided and detailed views.
It independently compares evidence values and packet identity with the saved
packet before displaying them. Altered values produce a visible error. Original
zero, null, empty and missing values remain distinct. Field-value hashes identify
canonical JSON transformations; packet hashes identify the original saved bytes.
Older reviews remain unchanged and are not relabeled as having captured sources.

Source fidelity is mechanically checked. Classification accuracy is still an AI
judgment, and the presence of a cited field does not establish that the issue is
real, causal or scientifically significant. The reviewed finite plan is not a
validated hypothesis. The latest acceptance and execution guards remain required.

Validation commands from `jumpserve-infra`:

```sh
npm run test:agent
npm run test:research:ideas
npm run test:research:ideas:browser-fixture
```

With that fixed local fixture running and a frontend build available, run these
sequentially from `jumpserve-front-end`:

```sh
npm test
npm run lint
npm run build
npm run verify:research:ideas -- --review-sources
npm run verify:research:ideas -- --interview
npm run verify:research:ideas -- --guided
```

Set `JUMPSERVE_BROWSER_CSS_PATH` when the build is in an isolated checkout. The
browser fixture uses actual components/API/agent/Postgres, with explicit synthetic
authentication/provider/cloud boundaries. The guided suite executes six actual
fixed loopback HTTP requests; these are software checks, not CDN science.

The predeclared bounded live evaluator is:

```sh
python3 -B test/evaluate_research_ideas.py --live --source-review
```

It verifies AWS account `395567831870` and repository Supabase target
`regphejnlvfpyokpniny`, calls native Bedrock, stores original SDK/CLI bytes,
server-rendered answers, source hashes and usage, and makes no database writes.
Provider failure diagnostics are retained privately; their hashes and bounded
error classifications may be shared. Missing charges are unknown, not zero.

Protocols, amendments, failed candidates and actual answers are preserved. The
21 cases are exposed/tuned development checks reviewed by the AI implementer,
not independent, human or held-out validation. See
`idea-review-source-fidelity-validation-v1.json` for the current result.

The v11 seed remains an unpublished draft. Its migration requires all 21 named
cases and hashes of original model and rendered answers before publication.
This local fix does not authorize deployment. A future authorized release must
verify the AWS/Supabase targets again, apply additive migrations, deploy the
compatible agent while retaining the old active prompt, publish only the eligible
exact candidate, release the frontend, and verify a legitimate authenticated chat
and production persistence. No production prompt pointer was changed here.
