# Platform Development Supervisor OpenClaw

This is a private platform maintenance service for the three JumpServe
repositories. It is separate from paper assessment planning, execution and
scientific conclusions. The user authorized qualified automatic merges and
production deployments by this named service. Initial activation remains a
separate explicit deployment step; ordinary interactive sessions retain their
existing deployment rules.

The current implementation is local. No production migration, IAM change,
repository protection change, merge, application deployment or worker installation
has been performed by this implementation session.

## Operation and authority

`platform_supervisor/worker.py` runs on the existing subscription host with a
separate spool and systemd service. Research gets priority between scheduling
slices. A shared database lock prevents both services from admitting native tools
at once. Uncertain container cleanup keeps host admission fenced. The existing
worker, research runtime, subscription grant and encrypted disk are preserved.

After an owner resumes admission, the worker accepts owner-queued objectives and
at most one automatic maintenance task per rolling 24 hours. Maintenance has a
six-hour deadline and a $100 conservative reservation limit. A model call reserves
$1 before transport. These reservations are admission units, **not measured
charges or a complete AWS billing cap**. Actual subscription allocation, host CPU
credits, egress and image build charges remain unknown. Defaults do not reset
when a task is cancelled or a process restarts. There is no paid model fallback.

The platform owner allowlist is a private bootstrap input. The four supplied
addresses are not included in source, CI variables, public PR descriptions or the
runtime bundle. Supabase enrolls verified Google users by their actual `auth.users`
identity and confirmed email. The browser cannot choose an owner ID or role.
Owners can queue, cancel, pause/resume and enable/disable automatic releases.
The viewer role reads records without control rights. Revocation requires removing
the enrollment and setting the bound operator role to `revoked` through an
administrative operation. Its identity/history remain intact, and self-enrollment
cannot reactivate a revoked row.

Original prompts, response streams, artifact bytes, run IDs, external action
intents, test receipts and release proofs are separate versioned Supabase records.
Original terminal model outcomes and history are immutable. Reconciliation appends
proof rather than rewriting an unknown original. Missing usage and zero values
remain distinct. Artifacts are private, content addressed, read back after upload,
and verified on download. Bounded dashboard pages do not imply complete history.

## Persistent AWS authorization

Production operation never uses a human CLI profile or a long-lived AWS key:

- The EC2 instance profile supplies refreshable credentials. The platform service
  rejects static AWS environment credentials and SSO profiles. It reads the
  Supabase and publisher service secrets outside the coding container. Secrets
  are refreshed from Secrets Manager after a five-minute cache interval.
- Infrastructure/frontend release jobs exchange a GitHub OIDC token for
  `JumpServePlatformRelease`. Trust is restricted to this account and the exact
  infrastructure repository's `main` subject. Its two-hour session exceeds the
  workflow's 90-minute limit. Each new job obtains a new session without human
  login. The backend image path uses the existing backend-main OIDC image role.
- CloudFormation uses `JumpServePlatformCloudFormation` for the two existing app
  stacks. Its permissions exclude IAM changes, EC2 launches and storage changes.
  The service cannot deploy its own access stack or expand these permissions.

The initial bootstrap uses the operator's named AWS profile once to install these
roles. Subsequent service operation does not depend on that profile's lifetime.
See [AWS instance roles](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)
and [GitHub OIDC on AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

## Coding, checks and release scope

OpenClaw edits plain copies at exact repository revisions. Its tools are read,
write, edit, exec and process inside an image pinned by digest, with no network,
host socket, cloud credentials, publisher credential or host home directory.
Dependency installation runs separately with public outbound access, no lifecycle
scripts and no credentials. Installation must verify IMDSv2 with hop limit one so
dependency containers cannot obtain the host's role credentials.

The trusted controller retrieves public Context7 documentation through its remote
MCP server before code generation. It resolves library IDs before querying docs,
retains the requests and responses, and delivers references in the workspace.
Public documentation can be cached for 24 hours. Additional bounded topics use
`documentation-requests.json`. An optional Context7 API key can be stored in the
private service secret; anonymous access passed the local integration check.
Documentation outages schedule a retry before admitting more coding calls.
The Next.js repository's installed guides remain part of its coding instructions.

The controller freezes changed files, hashes source, runs fixed checks and checks
that tests did not mutate that source. It publishes matching Git objects and a
stable PR branch. Public PRs contain changed paths, test identities and task IDs;
private objectives and account addresses are not copied into their descriptions.
Strict up-to-date branch protection and a successful GitHub Actions **Platform
validation** check at the exact head are required. Administrator enforcement is
required; there is no bypass merge path. New base revisions trigger a fresh source
copy, retained candidate/conflict files, repair and another complete check cycle.
Existing tests, authority, CI, schema and scientific policies cannot be weakened
by an automatically published change.

The current automatic production adapters are:

| Component | Release and actual revision proof |
| --- | --- |
| Frontend | Amplify's main build; exact successful build commit, public `/api/platform-version` match and HTTP smoke check |
| Benchmark backend | Existing pinned AMI build, success/failure ingestion checks, selected production launcher image and live image/source receipt |
| Existing infrastructure | Credential-free synthesis, guarded changes to existing Lambda/API/event/log resources, scoped CloudFormation update and exact deployed template comparison |

New IAM/compute/storage identities, SQL migrations, worker changes, evaluated agent
changes and qualified research/real-world runtime pins require their dedicated
release procedures. A task proposing one retains its source and exact blocker;
it does not quietly send it through a broader deployment. This version does not
automate every possible repository change. Scientific qualification and frozen
criteria remain required. Cross-repository releases are recorded separately and
are not an atomic transaction.

A merge, submitted workflow or successful CI job is not completion. Every
applicable component needs an exact production verification receipt. A lost
workflow acknowledgement is resolved by its original operation ID and workflow
run; it is not blindly redispatched. Unknown model streams are never replayed.
Pausing/cancellation stops new admissions at safe boundaries. Already admitted
releases can finish; their actual results must reconcile before a terminal task
outcome. Cancellation does not undo an existing merge. CloudFormation handles its
native rollback; the existing AMI workflow retains its guarded rollback and cleanup.

## Dashboard

The header links to `/platform-updates`. Google sign-in resumes that private URL.
Only configured operators can read its queue, details, event history, prompts,
responses, artifacts, PRs and release receipts. Other signed-in Google users are
denied. SQL tables remain private; checked RPC projections and private Storage
downloads are used. Supabase Realtime follows the operator SELECT policy, with
polling recovery. Control request identities survive a browser reload in session
storage; uncertain requests retry the same identity.

## Initial activation order

Do not invoke these mutations until the user explicitly requests deployment of
the current implementation. The review packet is in ignored local artifacts,
including private enrollment inputs; never commit that packet.

1. Finish the local checks and prepare the exact source packet with
   `python3 -B bin/platform-supervisor.py prepare --owners-file <private-file>`.
   This reads existing AWS configuration and renders the separate access stack;
   it does not modify remote state. Preparation verifies the existing GitHub
   OIDC subject format.
2. Commit/publish the platform changes independently of unrelated local research
   changes. Verify all three new validation workflows at their intended heads.
   Do not include the uncommitted research recovery work merely because it shares
   this workspace. The frontend's initial build and release identity must be
   verified explicitly.
3. Run the `protect`, `migrate` and `access` bootstrap actions with the reviewed
   private packet. Migrations 004–006 install private control/data records and
   host coordination. The authorization starts paused. The access action deploys
   only `JumpServePlatformAccessStack`, preserving the existing worker.
4. Apply the separate fixed-target `harden` action and verify IMDSv2 is required,
   with hop limit one in applied state, before adding platform service credentials.
   This changes metadata settings in place and does not replace or reboot the
   worker. Preparation records the original settings; installation refuses an
   unsafe setting. Reverify this operational setting after any later explicit
   OpenClaw stack update.
   The `install` action verifies the passed live tool-image control, validates the
   private GitHub service credential's repository access, creates its service
   secret if needed, uploads content-addressed bytes and submits one recorded
   fixed-target SSM installation. An uncertain SSM acknowledgement must reconcile
   by its original comment/command ID. It must not submit another installation.
5. Verify the SSM result, actual loaded image digest, service, runtime/source
   hashes, IMDSv2 hop limit, instance-profile credential method, private owner
   access/denial, publisher permissions, heartbeat and OIDC roles in production.
   Confirm the installed host-coordination wrapper against the actual research
   dispatch chain. A successful submission is not a successful installation.
6. From an authorized Google session, resume admission and perform a bounded
   end-to-end release control. Verify the actual production revision, retained
   Supabase evidence and remote controls before describing the service as active.

Use the dashboard to disable releases or pause admission during investigation.
Keep original records, versioned installation directories, failed reports and
action identities. Do not replace the existing subscription host or copy/rotate
its grant as part of installing this service.

## Local evidence and limitations

The implementation session verified the frontend build and 283 unit checks, six
desktop/mobile browser cases, isolated PostgreSQL control/lease/history/security
checks, controller recovery fixtures, scoped-template/role checks and a real
OpenClaw/Docker software repair with **six complete subscription responses**.
The repaired fixture preserved its acceptance script and passed numeric, zero and
missing-value controls. A separate public Context7 MCP request succeeded without
an API key. These are software development checks, with nonindependent AI review;
they do not establish scientific validity or production activation.

Retained local native control:
`jumpserve-back-end/.test-artifacts/platform-native/20261031T000138602233Z/report.json`.
Native tool execution used the built Linux/amd64 image. Later controller,
documentation and authority changes have separate local regressions; the live
control is evidence for the captured coding path, not a claim that every final
orchestration branch executed against production services. SQL fixtures use
synthetic Google identities/Storage and an isolated research-claim transport.
Browser fixtures use the real component and built CSS with synthetic auth,
API and Realtime boundaries. Live Google OAuth, OIDC role assumption, actual
publisher mutation permissions, deployment/rollback and Supabase Storage remain
initial activation verification steps.
