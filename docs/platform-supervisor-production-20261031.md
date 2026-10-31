# Platform supervisor production activation — 2026-10-31 UTC

The explicitly requested rollout installed and activated the separate AWS
platform service and private [Platform Updates dashboard](https://jumpserve.quaint-lab.org/platform-updates).
This record distinguishes actual production checks from local and synthetic
controls. Account enrollment inputs, credentials, original prompts and detailed
artifacts remain private.

## Installed production components

- Frontend baseline `ad3a4b2d6bfa3f743208ed3501f55bb3792c9a9c` passed
  Amplify job 132. Its public version endpoint matched that exact revision and
  the public home page passed an HTTP smoke check.
- Supabase migrations 004–006 installed thirteen private RLS tables, private
  content-addressed artifact storage, immutable authorization and coordination
  with the existing research dispatch function. Production checks confirmed no
  anonymous table reads or browser writes and no legacy dispatch bypass. The
  original research function body was preserved.
- The private enrollment list contains four Google accounts. Three existing
  verified Google identities were bound and passed owner-claim checks; the
  remaining account enrolls on its first verified Google sign-in. An unknown
  Google identity was denied. A fresh interactive OAuth round trip was not
  exercised during activation. Unauthenticated dashboard API access returns 401.
- `jumpserve-platform.service` is enabled and active on the existing AWS host.
  Its loaded files match runtime bundle
  `09441030f8c5808eca4e0d332263ae4816d15a1628c7deb2b96940cd49d38c22`.
  The immutable policy remains `platform-supervisor-v1.1`, SHA-256
  `ac9acc0b71aa258d924d3bc5b0ea90ff16597a84c26ec65236103cbc383ce5a3`.
  The research service remained active and its runtime source hashes were unchanged.
- The running service reports the SDK credential method `iam-role`. EC2 metadata
  requires IMDSv2 with hop limit one, in applied state. No human SSO profile or
  static AWS key is used by the service. It continues when the operator computer
  is off. Revocation of publisher or model-provider grants can still require
  account recovery; AWS role renewal itself does not require human login.
- Strict administrator-enforced `Platform validation` protection is installed on
  all three repositories. The actual worker publisher can push and read that
  protection in each repository. Coding containers do not receive those credentials.

## Executed controls

The [scoped release workflow](https://github.com/jumpserve-networks/jumpserve-infra/actions/runs/41159571104)
actually assumed the AWS release role through GitHub OIDC and produced the
baseline frontend's exact production receipt. This did not depend on the local
AWS profile. It verifies that frontend release path; it does not claim a new
backend AMI, infrastructure application update or rollback was exercised.

The pinned tool image was built and exercised on the existing AWS host. Six
actual subscription responses repaired a software fixture while preserving its
unchanged numeric, zero and missing-value acceptance checks. The original control
stopped at its admission cap after retaining completed source. Its failed report
and task remain intact; a separate reconciliation passed with zero new provider
calls. Two subsequent real OpenClaw/Docker slices used synthetic transport to
verify retained files and complete container cleanup, also with zero provider calls.

The reviewed controller correction in
[backend PR 9](https://github.com/jumpserve-networks/jumpserve-back-end/pull/9)
separates model-call admission from fixed validation of retained source. No model
allowance or deadline is added by that correction. Failed fixed checks retain a
budget outcome; successful checks still require scope guards, protected exact-head
CI, merge receipts and actual production verification.

## First autonomous improvement

The initial heartbeat improvement is task
`50de9ff2-8ee5-460e-8855-ac72a67df013`. It consumed its original twenty model-call
admissions; all outcomes are recorded, including one definite tool-proposal
failure. Its original deadline is `2026-10-31T03:37:26.452527Z`. A distinct
bootstrap event preserved its earlier budget outcome before admitting fixed
validation of already retained source with zero provider calls remaining.

The AWS controller then passed dependency installation, lint, 291 frontend tests
and the production build for its frozen source. It published
[frontend PR 4](https://github.com/jumpserve-networks/jumpserve-front-end/pull/4),
waited for [exact-head GitHub CI](https://github.com/jumpserve-networks/jumpserve-front-end/actions/runs/41164176034),
and merged revision `c90dfba1650083077f14466681f55820d6a1a5f1` itself.
The change preserves the original heartbeat timestamp and worker message while
adding fresh, delayed and unavailable states, including boundary and rendering
tests. No further provider call was admitted during validation or publication.

Amplify job 133 deployed that exact merge. The
[OIDC release workflow](https://github.com/jumpserve-networks/jumpserve-infra/actions/runs/41164284017)
verified the live `/api/platform-version` revision and public HTTP smoke check at
`2026-10-31T03:27:35.979888Z`. The worker retained that bound production receipt,
confirmed its original publish/merge/deploy operations and recorded the task as
completed at `2026-10-31T03:28:10.014670Z`. Its twenty-call reservation and original
deadline were unchanged. This verifies a cloud-hosted coding, fixed-check, PR,
protected-CI, automatic-merge and frontend-production path after the documented
bootstrap repairs; it does not imply those repairs or every component release
were unattended.

The initial task occupies the first daily maintenance slot. Subsequent automatic
maintenance is limited to one task per rolling 24 hours; owners may queue work
and use the dashboard's pause, cancellation and release controls. Current release
scope and remaining dedicated-release requirements are documented in
[platform-supervisor-v1.md](platform-supervisor-v1.md).

Private source packets, SSM command IDs/results, source hash comparisons, SQL
security checks, model outcomes, check artifacts and release proofs are retained
in Supabase and the ignored deployment artifact directory. Earlier failed controls
remain historical evidence and are not rewritten as successes.
