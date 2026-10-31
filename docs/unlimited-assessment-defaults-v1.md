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

## Prepared future default

The future-default release is prepared locally; it is not active merely because
the existing assessments have been amended. Migration
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
behavior remain intact. Legacy $100 defaults stay readable during rollout.

## Validation and release boundary

The qualified default uses backend revision
`06a163322ebb07c010c2d40a7caffde2b341a1ec` and source binding
`17d0e6a9bc89fc68481719dab2a1de681d53418df70fcd5f7aff476bfb3d1ff6`.
Its dedicated deployment profile changes only the code assets and their matching
CDK asset-path metadata for the API,
autonomy controller and queue controller. The package executor, ingestion,
cleanup, immutable executor version and every IAM policy retain their deployed
content. The renderer rejects other runtime-source changes and controller
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

Local validation includes 398 backend tests (four environment-dependent skips),
295 frontend tests, lint and the production frontend build. The isolated
PostgreSQL check executes the existing audited-amendment and unknown-call tests,
then exercises the new standing policy, active-assessment preservation, new
intake, actual public API projection and browser/runtime policy-write denial.
It uses no provider call or AWS resource. Docker stays stopped.

Do not push, merge, migrate the default, or deploy these application/runtime
changes until the user explicitly requests deployment of the current changes,
as required by the repository deployment workflow. Before production activation,
qualify and pin the exact changed runtime files, retain the declared source and
checks, deploy the compatible frontend/backend with safe admission coordination,
apply the reviewed migration, and verify new intake plus existing live budgets.
Do not copy unrelated uncommitted research recovery work into that release.
