# Category budgets production activation — 2026-10-31 UTC

The explicitly requested release activated Supabase category budgets and the
compatible frontend, platform supervisor and research controllers. Verification
completed at `2026-10-31 19:51:25.719719+00`. Current limits and the immutable completion receipt are
available in private [Platform Updates](https://jumpserve.quaint-lab.org/platform-updates).

## Applied policy

All four `public.autonomy_budget_categories` rows have `max_spend_cents = -1`
and `max_model_calls = -1`: `research_assessment`, `platform_manual`,
`platform_maintenance` and `platform_repair`. The sentinel means unlimited;
zero remains finite. Future edits are audited and current policy is read at
admission. Workers can read policy and cannot increase their own budgets.

Migration `202610310003_category_budgets.sql`, SHA-256
`52bf304c66e8b47ae6b97bf575965cacf8e1b14d56578c530f09fff595ac04d6`,
was applied only to JumpServe project `regphejnlvfpyokpniny`. Live checks verified
the four rows, private RLS/ACLs, revoked legacy service entry points and retained
assessment deadlines, prompt hashes and nondecreasing usage. Historical stopped
or expired work is not restarted merely by removing a budget.

## Released source and actual revision proof

- [Frontend PR 6](https://github.com/jumpserve-networks/jumpserve-front-end/pull/6)
  merged `45cfec90e67d31cbafaf7710501f94d255c3d378`. Amplify job 135 succeeded;
  the live version endpoint matched. The existing GitHub OIDC release workflow
  [verified that production revision](https://github.com/jumpserve-networks/jumpserve-infra/actions/runs/41235327269).
- [Backend PR 11](https://github.com/jumpserve-networks/jumpserve-back-end/pull/11)
  merged `2853939890f626e66d55260c70c5ff0e0334a930`; runtime manifest 76 pins
  qualified source `3906d7224857b296586fe50af257a99f5922837f`.
- [Infrastructure PR 27](https://github.com/jumpserve-networks/jumpserve-infra/pull/27)
  merged the policy migration. [PR 28](https://github.com/jumpserve-networks/jumpserve-infra/pull/28)
  merged the qualified runtime release at
  `9837c70b3bac395ecd35a1ccb8be77f2048c726e`. Protected exact-head checks passed
  before each merge. An earlier failing historical-fixture regression is retained;
  its correction freezes the old release's original v75 inputs and keeps every
  acceptance assertion when the current runtime advances.
- The dedicated controller update settled at `UPDATE_COMPLETE`, template SHA-256
  `03ec38b84f88021360634c655678116f57445caad06a9e3426301b2ee44585d3`.
  All three actual Lambda ZIPs matched the committed runtime files. Only their
  code objects, two category-policy flags and the obsolete autonomy description
  changed. Every experiment executor/version, IAM resource, parameter, output and
  other template property retained its original value. This was an authorized
  interactive release using the existing scoped CloudFormation execution role;
  it was not a general supervisor infrastructure release.
- The existing AWS host installed platform bundle
  `338bca32421b54fc4a02b4d71fa5e11cc1f9d920fb990b681618e956722b5d97`.
  Readback verified every installed source file and both active services. The
  research service was not restarted. IMDSv2 remained required with hop limit
  one, in applied state. The installed credential guard requires renewable
  instance-role credentials; no static AWS key or human profile was added.

## Actual cloud controls and retained failure

The research control made one data-only response through the existing AWS model
worker. It honestly returned blocked for missing source data and launched no
experiment or paid fallback. Its completed response was retained, the software
fixture was closed without replay, and private evidence archive SHA-256
`6b3ec7707cf107b0a211f0d59d793e8428039fb96e362c25b5a1f4a8781f3fca`
was retrieved and verified. The qualified source binding is
`e4637cd12044f0289a8ee9533fc76b8817f69b4724e91a26eec058f59a560f31`.
Other runtime/scientific-criteria bytes retained their prior qualification.

The platform fixture recorded six complete responses and ready source with the
original numeric, zero and missing-value checks unchanged. Its first final check
failed because the container default UID could not read the private workspace.
Original task `568fa78f-1daa-5e4f-90ab-8073f95d13f7`, its failed report and six
responses remain unchanged. The corrected harness runs the check read-only using
the host worker UID/GID. A separate reconciliation,
`d0855f03-4658-57d5-a0ab-825c3baa95f6`, verified the retained source with provider
transport disabled and **zero additional provider calls**. It checked identical
worker bytes and the unchanged pinned tool image/acceptance criteria and retained
a separate passing report. No trial allowance, usage counter or deadline was
reset. An installation readback submitted before installation finished remains
as an early failed observation; a separate readback after the successful original
installation confirmed the final source and services.

## Live behavior and remote monitoring

The actual public capability response declares category policy revision 1 and
both unlimited assessment limits. Assessment `444d171c-2fac-4ba9-b33c-2b46304cb0ec`'s
actual shared-queue response passed the released frontend validator, retaining
13,100 committed cents and its original `2026-11-07T03:55:29.960611Z` deadline at
verification. Existing scientific labels and other blockers remain independent
of this budget release. The private dashboard API still returns 401 without a
session; a fresh interactive Google OAuth/PDF-upload round trip was not exercised.

The original platform admission and automatic-release settings were restored.
Fresh AWS worker heartbeats were verified. Completion event
`7a12fe7f-3f93-5dfe-8f9e-18e8dfc334cc` records the limits, exact releases,
qualification evidence and restored controls in Supabase. Detailed private source
packets, original command identities/results and readbacks are retained in
`.test-artifacts/category-budgets-v1/`. The service continues on AWS when the
operator computer is off. Later unrelated interactive releases still require
new deployment authorization under repository guidance.
