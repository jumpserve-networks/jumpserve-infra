# Claim designer production release

Released 2026-10-18 UTC at https://jumpserve.quaint-lab.org. All feature changes
were committed and pushed to main in the frontend, backend and infrastructure
repositories. The website, research API, agent, thirteen database migrations and
reviewed v6 prompt are active. Release-blocking checks passed; the conditional
authenticated and networking checks below remain explicitly unverified.

| Component | Released identity | Verification |
| --- | --- | --- |
| Backend | `4266de647fe4f61658d0ce53a5d976b81507648b` | All sixteen declared source files match all five deployed research Lambda ZIPs. |
| Infrastructure application | `e582da2` | Scoped Benchmark/Agent deployments completed; existing stack parameters and agent dependency layer preserved. Later release-tool/documentation corrections do not change deployed runtime bytes. |
| Frontend | `bda33aaefc529b84f6935ce954fbe887ef2386ae` | Amplify app `d24jvguj7brnkj`, main build **114**, BUILD/DEPLOY/VERIFY succeeded. Later verifier/documentation-only commits use skip directives. |
| Prompt | `research-claim-design-v6`, `3da220d0-cde0-5ab5-b8cd-ccbd23ece025` | Active, published at `2026-10-18 02:48:47.940812+00`; content SHA-256 `581cea6ac6b03ff161b81c2f44e20282e56e32cced5064fed7e89ab39f2ebd64`. |
| Targets | AWS `395567831870`/us-east-1; Supabase `regphejnlvfpyokpniny` | AWS caller, fixed project URL, live project identity and database verified before changes. |

The [declared release protocol](claim-design-release-protocol-v1.md) separates
software readiness from scientific coverage. The [release evidence](claim-design-production-release-evidence/)
contains migration hashes/statuses, original successful and failed receipts,
deployment logs, source/hash verification, build metadata, browser reports,
exports, screenshots and AI visual review. Its versioned artifact manifest
records original bytes. The separately retained
`claim-design-production-release-storage-v1.json` records the final private
release-archive retrieval check, without creating a self-referential archive.

## Enabled workflow

From a published paper assessment, **Design an experiment for this claim** opens
or resumes an authenticated private workspace bound to that exact claim and source.
For gaps without a retained executable plan, **Run experiment now** offers the same
design path. Existing retained-plan execution continues to use its prior queue path.
The designer asks for missing decisions, keeps clarifications separate from
adoptable candidates, preserves supplied settings and shows exact unit-conversion
provenance. Adoption, fresh comprehension/critic reviews, owner acceptance,
freezing and queueing remain distinct recorded steps.

The supported automatic emulated and real-world runners remain enabled with their
existing limits. Custom-package admission remains disabled, matching the reviewed
production configuration. Missing implementations, source identities, specialist
equipment and domain decisions remain visible work. No universal inferential
engine or automatic scientific verdict is enabled by this release.

## Verification and boundaries

Local release verification repeated 122 backend, 116 agent, 180 frontend and 89
infrastructure tests, six claim-design SQL groups, eleven existing-idea SQL groups,
ten integration browser groups, lint and both builds. The existing
`auth-button.tsx:153` navigation warning remains. A fresh offline replay matched
all twenty original provider/raw/rendered identities against the reviewed report;
it made no provider calls. Local browser authentication/provider/Storage/cloud
dispatch were explicit fixtures; actual React/API/agent parsing/Postgres code ran.

Production verification checked RLS and browser write denial across all 28 research
relations, the new private claim context and restricted RPCs, the final publication
guard, private originals, evaluated prompt identity and deployed ZIP/source hashes.
Six unsigned private/model requests returned 401, including GET/POST claim-design
routes. The deployed Python 3.12 handler responds, but this does not verify every
authenticated execution path or its boto3 provider call.

The final production browser campaign passed all five check groups. It verified
all fifteen IPv6 claim-design links and their exact sign-in destination, four
private-route return paths, visible invalid-ID 404s, desktop 1365px/mobile 390px
light/dark gaps pages without horizontal overflow, the 3,494,894-byte public export,
missing-study/export states, landing buttons, previous assessments and methods.
Screenshots were inspected by the primary Codex AI implementer, not a human or
independent usability reviewer. The browser made no mutation requests, model calls
or experiment submissions. Existing numerical charts were not separately exercised
in this production campaign; their prior local/result-module checks are not
relabeled as new production chart verification.

Remaining conditional checks:

- A legitimate Google-authenticated planning request through production
  boto3/provider/persistence, including cross-owner behavior in a real session.
- The authenticated plan-artifact Storage path. A private release-artifact
  upload/download/hash and anonymous-denial check passed, which has a narrower scope.
- Actual networking execution from an adopted, reviewed and frozen new plan.

No legitimate Google session was available to this clean verification browser.
Users were not impersonated and no networking job was submitted to substitute for
these checks. A completed networking experiment still needs its own reviewed
scientific protocol, budget, inputs and measurements.

## Evidence integrity and corrections

All 268 initial, 166 correction and 379 follow-up archived evaluation artifacts
were hash-verified unchanged. The original failed candidates remain archived. The
actual v6 live pipeline result remains **19/20**; the exact corrected deterministic
replay passes **20/20**. These are exposed development checks with non-independent
AI evaluation/review, not held-out or human validation. The publication report
retains that distinction, parent/provider/request identities and original failed
unit-case status. See the [evaluation report](claim-experiment-design-followup-v3.md).

The evaluation originals were uploaded to private bucket `research-workflow-raw`,
object `release-verification/claim-design-20261018/12736e4a3f52fccf477a0c8f678fa442b1c6745dd928570f683f93d632e86771.zip`:
9,991,706 bytes, 863 files, SHA-256
`12736e4a3f52fccf477a0c8f678fa442b1c6745dd928570f683f93d632e86771`.
Retrieved bytes matched exactly; anonymous read returned 400. The publication
history stores the reviewed report and storage provenance.

Failed release checks were preserved separately. An initial sandbox network denial
was retried with scoped approval. A release logger used an absent default GET
method attribute; `Request.get_method()` corrected the reporting error. The first
production browser run used link-role selectors for Base UI button-role anchors;
the corrected verifier checks their actual role, label and href, and passes. No
application code was changed for those verifier failures. One sandbox browser
attempt also failed before network access and remains recorded.

The initial per-deployment verifier reused before/after ZIP filenames. Independent
initial-inspection copies retained all six exact pre-deployment archives; they were
matched to the recorded prior hashes and copied to separate recovered-before
directories. Original receipts remain unchanged. Future deploy commands now use
separate before/after directories. The preservation record identifies each source,
copy, hash and byte count; rollback originals remain in private local archives.
Original CDK asset identities remain in the diff logs; their remote retention was
not separately rechecked. Original Lambda ZIPs are not committed into public evidence.

## Scientific coverage and usage

This release makes no new scientific claim assessment and adds no networking
measurement. Migration receipts show unchanged counts of 7,144 research
measurements, 5,093 published values and 102 assessments before/after migration;
unrelated prompt pointers were preserved. Software deployment and numerical model
regressions do not establish correctness, causal validity, generalization or
operational effectiveness for a paper claim.

Deployment verification made zero new model calls and started zero experiment
instances. The prior v5/v6 development campaign's 201,140 input and 12,254 output
tokens are historical usage, not counted again by replay/release. Build 114 lasted
149.774 seconds in total; its BUILD step lasted 124.416 seconds. Lambda memory,
timeouts, runtime identities and artifact bytes are recorded in receipts. Measured
charges, estimates, local compute/storage allocation and authoring/reviewer model
usage remain unknown, not zero. No unobserved managed-build compute type or
per-request billing allocation is invented.

Reproduction commands and current target guards live in
`bin/claim-design-release.py`; read-only modes include `inspect`, `verify` and
`frontend-status`. The public browser verifier is
`jumpserve-front-end/scripts/verify-claim-design-production.mjs`. Original local
protocols and commands remain in the evaluation reports. Deployment and publication
are explicit mutation modes, not steps to rerun merely to reproduce analysis.
