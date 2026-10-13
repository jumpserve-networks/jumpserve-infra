# Research workflow and claim queue: production release protocol v1

Frozen 2026-10-07 before production changes. The user's current explicit production
deployment request authorizes this release. Earlier implementation protocols,
failed results and amendments remain unchanged. This is software release
verification, not a new scientific campaign or independent validation.

Targets: AWS account 395567831870, us-east-1; Supabase project
regphejnlvfpyokpniny; frontend https://jumpserve.quaint-lab.org. Verify actual AWS
identity and the guarded Supabase Management API project before mutations. The
available Supabase MCP connector reports a different project and must not be used
for JumpServe changes. Stop mutations on target mismatch or expired credentials.

Release blockers: preserve and verify prior passing source-byte manifests and
database/browser evidence; pass backend and frontend regressions; pass frontend
lint and production build; pass infrastructure build and tests; stage exactly the
pinned research runtime bytes; inspect the CloudFormation diff for unrelated
deletions/replacements; apply original and additive queue migrations only if
absent; verify all 20 relations have RLS and expected read/write restrictions,
service-only RPC access and private original storage; deploy API/workers before
frontend; verify live public API, missing data, unauthenticated write denial,
frontend desktop/mobile navigation, methods/queue examples, themes and correct
Google sign-in return paths. Failures and follow-ups retain separate evidence.
Existing validated application bytes may reuse earlier checks when unchanged;
release configuration and any corrections receive relevant fresh checks.

Conditional checks: actual owner intake/enqueue/review/cancel and cross-owner
denial require legitimate Google sessions. Never forge an authenticated identity.
Remote original-byte round trips and scheduled workers require valid AWS/Supabase
credentials; verify private synthetic software fixtures when feasible, clearly
separate from public science. Inspect deployed Lambda byte hashes, configured
memory, concurrency, timeout and one-minute schedule. Idle scheduled polls verify
hosting invocation, not successful queued execution. Completed scientific pages,
charts/exports and invalid-data states already have isolated browser evidence;
if no genuine public study is present, record that production-specific gap rather
than publish synthetic science or fabricated reviews. Generic AI chat remains
disabled: no evaluated generic prompt candidate exists.

Controls: preserve unrelated staged user PDFs and existing modules. Only declared
numerical arithmetic is automatic; no arbitrary submitted code, EC2 experiments
or model evaluations are enabled. Claims retain separate scientific assessments.
Queue completion/discrepancy must not upgrade labels. Do not import or publish a
new paper assessment as a side effect of infrastructure deployment.

Bound resources: API 512 MiB/29 s/reserved concurrency 4; worker 512 MiB/180 s/
reserved concurrency 2, two slots per poll, global 4/study 2 running jobs,
600-second fenced lease; 256 KB originals/1,000 observations/10-second numerical
adapter; one-minute schedule without automatic experiment retries. Browser checks
use one sequential session with desktop 1365x900 and mobile 390x844. No statistical
interval is estimated from software checks. Model usage is inapplicable to this
release; charges, peak memory and otherwise unavailable usage remain missing.

Stop after declared blockers and feasible conditional checks pass. On a new defect,
preserve failed evidence, document a versioned correction, rerun affected checks,
and do not publish until blockers pass. Rollback disables queue scheduling or
restores the previous frontend/API release while retaining migrations, original
bytes, job/event history and scientific evidence. Record exact revisions,
migration hashes/apply receipts, deployment IDs and actual verification scope in
a new release report. Reviewer: primary Codex AI implementer, not independent;
no human review or held-out evaluation is asserted.
