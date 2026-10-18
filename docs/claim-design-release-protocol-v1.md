# Claim designer production release v1

Declared 2026-10-18 UTC after the user's explicit request to merge all current
changes to main and deploy production. This release does not amend the archived
scientific/model evaluation protocols or their failed and successful results.

Targets: AWS 395567831870/us-east-1, Supabase regphejnlvfpyokpniny,
Amplify d24jvguj7brnkj/main, https://jumpserve.quaint-lab.org.

Release blockers: exact reviewed v6 replay lineage and evaluated runtime hashes;
passing backend/agent/frontend/infrastructure tests and builds; local SQL security,
publication rejection/acceptance, ownership and queue checks; desktop/mobile
browser fixtures; clean committed backend runtime pin; reviewed scoped CDK diffs;
verified target identities; private originals and RLS/browser write denial. Apply
the thirteen versioned claim-design migrations in order, preserving all drafts and
unrelated active prompts. Deploy the compatible API and agent, verify their ZIP
and source hashes, archive original evaluation evidence privately and verify its
retrieved hash, then publish only the exact reviewed corrected v6 replay report.
Release the frontend after those checks. Verify its actual build commit and
deployed pages, authentication boundaries and new client code.

Conditional checks: an actual Google-authenticated planning request and production
boto3/provider/persistence round trip require a legitimate available user session.
Do not impersonate users or extract browser credentials. Actual networking jobs
require an adopted, reviewed, frozen experiment; do not run synthetic scientific
jobs for deployment verification. A private release-artifact Storage round trip
is required; it does not verify the authenticated plan-artifact path. Lambda
Python 3.12 imports and unauthenticated handling are checked on deployed services,
but do not establish that every authenticated path executed successfully.

Budget: zero new model calls, zero new experiment instances; at most 32 MB for the
original evaluation archive (plus a later bounded release-receipt archive), bounded
HTTP reads/timeouts, no automatic retries of mutations, <=30 minutes per stack
deployment. Failed actions retain receipts; stop and investigate unexpected
targets, permissions, configuration changes, migration state or source hashes.
Poll active builds at most once per minute. Record resources, tokens and costs
where observed; unknown model/compute/storage charges remain missing, not zero.

All three repositories are already on main; verify remote ancestry, commit all
feature changes with detailed messages, pin the exact committed backend revision,
and push without force. Evaluation snapshots remain immutable; deployment-only
runtime pin and documentation changes are recorded separately. Preserve migration
bytes, original Lambda ZIPs and provider evaluation artifacts. Rollback consists
of reverting application commits/deploying retained ZIPs and restoring the prompt
pointer through the existing audited publication mechanism; additive migrations
and scientific records are not deleted. The previous claim-design pointer is
empty, so disable the new entry point on rollback rather than fabricate a prompt.

Scientific coverage is unchanged: this releases a source-bound descriptive pilot
designer, not a universal inferential engine or a new claim assessment. Twenty
archived-answer replay checks passed after deterministic corrections; the original
live pipeline remains 19/20. These are non-independent AI-reviewed development
checks. Publication/deployment do not add independent scientific validation.
