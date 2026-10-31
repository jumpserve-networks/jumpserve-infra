# Unlimited aggregate budgets for active and future assessments

Operator instruction, October 31, 2026: **All active and future assessments**.
This extends the earlier assessment-specific authorization. It does not alter
platform-supervisor task budgets, scientific criteria, original seven-day
deadlines, per-experiment resource bounds, cancellation, provider quotas, unknown
outcomes, or the prohibition on a paid model fallback. Reservations remain
recorded admission amounts and are not measured charges.

## Active assessment authorization

The deployed, audited `research_autonomy_set_budget` RPC applied explicit null
ceilings to the four still-capped active assessments. One active assessment was
already unlimited. All five now have no aggregate spending cap. Original hashes,
deadlines, counters and commitments were preserved. Only safely budget-stopped
tasks were requeued; separately blocked and uncertain work was retained.

For `444d171c-2fac-4ba9-b33c-2b46304cb0ec`, both budget-stopped tasks were
requeued. Its separate UUID-validation and expired-lease/reconciliation blockers
were not relabeled or blindly replayed. Private authorization intents and verified
RPC receipts are retained in `.test-artifacts/assessment-budget-policy-v1/` and
the corresponding immutable Supabase amendment events.

## Live future default

The future default was activated in production on October 31, 2026 after the
explicit deployment instruction and verified frontend/backend releases. Migration
`202610310001_unlimited_assessment_defaults.sql` installs an immutable, private
standing-authorization record, makes new workflow ceilings explicitly null, and
retains an inherited-policy event for each new assessment. It serializes against
the real admission lock and uses the existing audited amendment RPC to catch
eligible assessments created during rollout. Completed, cancelled and expired
assessments are not restarted.

The latest intake implementation's initial-event funding metadata is updated
without replacing its authorization, lease or confirmation wrappers. Existing
initial prompts and historical limits remain unchanged. New API-generated
initial prompts and the versioned controller resource policy declare unlimited
defaults. A later explicit finite amendment remains enforceable.

The frontend accepts explicit null defaults and historical finite records without
treating missing values as unlimited. Confirmation terms use the assessment's
recorded cap and shared deadline. Intake request identities and one-submission
behavior remain intact. Historical $100 defaults remain readable.

## Validation and release boundary

The qualified default uses backend revision
`06a163322ebb07c010c2d40a7caffde2b341a1ec` and source binding
`17d0e6a9bc89fc68481719dab2a1de681d53418df70fcd5f7aff476bfb3d1ff6`.
Its dedicated deployment profile changes only the code assets and their matching
CDK asset-path metadata for the API,
autonomy controller and queue controller. The package executor, ingestion,
cleanup, immutable executor version and all benchmark-stack IAM policies retain
their deployed content. The renderer rejects other runtime-source changes and controller
runtime/authority differences. It starts from the deployed template, copies only
the qualified controller code pointers and matching asset metadata, and retains
all existing settings, including controller environments. The receipt lists
candidate controller settings that were retained from production. The general
release guard is unchanged. The profile requires the explicit
`qualified_defaults: true` workflow input and applies only to that fixed
qualified revision; it does not authorize future executor changes. Ordinary
supervisor releases keep the normal guard and do not inherit this one-time
deployment profile.

The dedicated update also freezes the existing nonsecret Ubuntu AMI and CDK
bootstrap parameter values. Both must match the reviewed profile and the actual
settled stack's `ResolvedValue`, then become literal `String` parameters with
those same values. The ordinary guard still rejects parameter-definition changes;
this dedicated step verifies precisely these two value-preserving conversions.
The final stack readback must preserve the captured parameter values. No SSM
permission is added and no AMI is refreshed. Keeping `UsePreviousValue` would
retain the SSM key and fetch its latest value, as described in the
[AWS parameter documentation](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/cloudformation-supplied-parameter-types.html).

The original code-only update reached CloudFormation but rolled back because
resolving an existing role's `Arn` requires `iam:GetRole`. The execution policy
adds only that metadata read, restricted to the same existing benchmark/agent
role namespaces as its Lambda `PassRole` permission. No IAM mutation permission
is added. The original rollback and matching AWS failure events are retained.
Release sessions continue to use GitHub OIDC; the one-time policy repair requires
an administrator credential because the release service cannot edit its own
authority.

The fixed image-builder role's output is retained as its exact recorded ARN.
The dedicated renderer checks the deployed role name, root path and actual
stack output before replacing that output's lookup with the same literal value;
the final readback verifies it. The CDK definition derives the ARN from its fixed
role identity. This avoids adding metadata access to the separately named image
builder role. Its policy, trust and identity remain unchanged.

The existing VPC security-group output is likewise retained as its recorded ID,
with its resource type, explicit VPC, original output reference and live value
checked. CDK emits the resource `Ref`, which returns the ID when `VpcId` is
specified, as documented in the
[AWS security-group reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ec2-securitygroup.html).
No EC2 metadata permission or network-rule change is introduced.

Local validation includes 398 backend tests (four environment-dependent skips),
295 frontend tests, lint and the production frontend build. The isolated
PostgreSQL check executes the existing audited-amendment and unknown-call tests,
then exercises the new standing policy, active-assessment preservation, new
intake, actual public API projection and browser/runtime policy-write denial.
Those local database checks use no provider call or AWS resource. Local Docker
remained stopped. Eleven release tests and the scoped CDK checks also passed,
including the actual deployment adapter with explicit cloud fixtures. These
software controls are separate from the actual production observations below.

## Verified production activation

One actual response through the existing AWS model worker qualified the changed
funding defaults and resource-policy instruction. The control reported missing
inputs honestly, made no scientific finding or experiment, and was closed after
its completed response was retained. Its archive SHA-256 is
`6ad3322c6113f3db3e892df00cff76c5b02774999f7f9304831f329c2267971d`.
Other runtime components retained their existing byte-bound qualification.

Frontend merge `dd1559d3b49ed7a67f543a82e257c5f3b4c3df6c` passed Amplify job
134 and its live version endpoint matched. The
[frontend OIDC verification](https://github.com/jumpserve-networks/jumpserve-infra/actions/runs/41213867923)
retains that exact production receipt.

The [infrastructure OIDC release](https://github.com/jumpserve-networks/jumpserve-infra/actions/runs/41220531700)
deployed revision `529aaca85fcc7dd6c7940f133af4d651dc58e9ad`, research runtime
manifest 75, and the qualified backend revision above. Its actual settled stack
and readback matched template SHA-256
`60ebcc0c94570d27c05dcd21114edda61246f5a39c0d66e4dade50a5ae8d7067`.
All recorded parameter and output values were preserved. The one-time IAM
metadata repair was read back and checked with AWS policy simulation: existing
application-role reads allowed; unrelated-role reads and IAM policy writes denied.

The applied migration's SHA-256 is
`8c06ed5cfa9b93a24fd47ec279a4bf49ce380c3af29b338672b1862bf60ae166`.
Production checks verified the immutable standing policy, private RLS and write
denial, and preservation of other research function bodies and ACLs. All eligible
active assessments were unlimited after activation.

Production intake control `ac4fea9c-b696-507a-81a8-fb39e06cbb2b` inherited the
null ceiling in its workflow, initial prompt and policy event. It was cancelled
inside the same admission-locked transaction, with zero model turns and zero
experiments. The actual public API response and the original assessment's public
queue passed the deployed frontend validators and produced uncapped funding
terms. Assessment `444d171c…` remained running beyond its former reservation cap
with its original `2026-11-07T03:55:29.960611Z` deadline. A fresh interactive
Google OAuth/PDF-upload round trip was not exercised by this release control.

The verified completion and original failure/rollback receipts are retained in
private [Platform Updates](https://jumpserve.quaint-lab.org/platform-updates),
Supabase qualification records, GitHub artifacts and the ignored
`.test-artifacts/unlimited-defaults-release-v1/` directory. Original failures were
not rewritten as successes. Unrelated local research recovery and traffic-limit
changes were excluded. Future interactive application or infrastructure releases
still require a new explicit deployment instruction under repository guidance.
