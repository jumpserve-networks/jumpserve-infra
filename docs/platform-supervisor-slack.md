# Supervisor Slack setup

## Workspace and shared conversation

- Workspace: QuAINT Lab, `dnagroupworld.slack.com`, `T01J887B6CE`.
- Private channel: [`#jumpserve-supervisor`](https://dnagroupworld.slack.com/archives/C0CEXNJE0HX), `C0CEXNJE0HX`.
- Initial DM owner: Michael Roger, `U06EL9LK476`, verified from his Slack profile link.
- Installed app: `A0CEQTE50TF`; bot user: `U0CEU87QZ5L`.

The private channel was created and verified on 2026-11-04. The owner and
Bradley Fang are members. The supervisor app was created, installed in QuAINT Lab,
and added to this channel. No other human invitations were issued by this setup.
Every human channel member should be able to mention the bot; channel membership
determines who can join the shared conversation. Do not add a channel `users`
allowlist that accidentally limits the group to the DM owner.

Use `@JumpServe Supervisor` to start a conversation, then continue in its reply
thread. Keep DMs separate from channel threads and from other users' DMs.
Group conversation access does not enroll participants as Google platform owners
or expose private owner conversation history.

## Shared operator controls (operations v2)

The 2026-11-04 follow-up requests broader supervisor and Slack authority. The
supervisor already holds standing permission to implement, qualify, merge and
deploy JumpServe improvements without another owner permission exchange. The
Slack operations v2 expands the original status/queue-only interface:

- `jumpserve_status`: live supervisor health, settings and shared tasks.
- `jumpserve_request`: queue improvements, runtime/self-repairs, tools and skills
  under the supervisor's existing standing authority.
- `jumpserve_task`: inspect a shared task's current blocker, progress, changes,
  releases and model-call states.
- `jumpserve_control`: pause/resume work, disable/enable automatic qualified
  merges/releases, or cancel a task shared in the conversation.

Every human member of the admitted channel receives these delegated controls.
An explicit operational instruction needs no additional owner approval or
confirmation step. Global settings affect the supervisor; task inspection and
cancellation preserve the existing channel/owner-DM separation. Controls record
the actual Slack actor and session under the owner delegation, never a fabricated
Google JWT. Replaying a request returns its original acknowledgement without
reapplying the action over a later command.

Credential protection, cancellation, private histories, scientific evidence,
fixed qualification and uncertain-action reconciliation remain in place. These
changes do not give a conversational model a credential-bearing host shell or
permit it to erase evidence or manufacture successful outcomes. Capability gaps
remain implementation work under standing authority, rather than reasons to ask
for another owner grant.

The owner explicitly requested and deployed operations v2 on November 4. The
initial v2 bundle was installed at 21:53 UTC and all four tools were verified in
the running configuration. Deployment requires the current explicit deployment
instruction in `AGENTS.md`. Apply the forward
migration `202611040002_platform_slack_controls.sql` after the original Slack
migration; do not edit the already-applied original. The v2 release packet lists
every required migration and hash. Both activation and runtime startup probe the
read-only operations contract and refuse to advertise the expanded tools until
that migration and the owner binding are available.

Local v2 qualification passed 126 database checks, 19 Python regressions, three
tool-transport tests, and pinned native configuration/plugin validation with all
four tools registered. The initial v2 bundle was
`ffffb34be4f7665b1357de100c77c993bef312ba0e7259f6960dc8345587d3e7`.
The first live control test supplied a zero UUID for the global `resume` action.
The gateway rejected that ambiguous target before dispatch; the subsequent live
status was honest about the failed control. The forward correction explicitly
declares a nullable optional task ID and accepts null for global actions. Cancel
still requires a valid task ID; non-null targets on global controls remain
rejected. The original failed tool call is retained, not relabeled successful.
Latest installation and conversation verification receipts are recorded as
versioned Supabase Platform Updates events. The
[capability kernel release record](platform-capability-release-20261104.md)
distinguishes operator installation from unattended recovery.

## Prepared configuration

`assets/platform/slack-app-manifest.json` defines the workspace app. Its scopes
cover app mentions, private channel history/info, the bot's DMs, basic user
information, posting and reactions. It does not request a human user token.
Socket Mode additionally requires an app-level token with `connections:write`.

`assets/platform/slack-channel-policy.json` is a **configuration fragment**, not a
complete runnable Gateway configuration. It admits the named private channel,
all its human participants and owner-only DMs. It disables bot-triggered turns,
automatic introductions, presence-triggered greetings and Slack configuration
writes. Replies stay in threads. Token fields contain environment references;
never commit actual credentials.

Both OpenClaw and its Slack plugin remain pinned to `2026.10.5`, with Node
`24.16.0`. The configuration passes the pinned CLI's schema check. Its runtime
loads the registered supervisor tools, and the official Slack plugin installation passes
the version, integrity and trusted-install checks.

## Verified credentials and gateway

Both credentials are stored in the dedicated AWS secret
`jumpserve/platform-supervisor-slack`, account `395567831870`, region `us-east-1`.
The app-level token has `connections:write`. Slack accepted both credentials,
confirmed the bot's workspace and app identity, and confirmed membership in
`C0CEXNJE0HX`. Neither credential is in source, CLI arguments or evidence files.

A read-only SSM preflight confirmed that the existing host's **instance role**
can read the secret, and that its Node/OpenClaw versions match. The existing
service policy already covers this secret; no additional IAM grant was needed.
The Slack service has a 2-GiB memory limit. The initial 1-GiB limit caused
confirmed cgroup OOM failures during native Gateway startup; the unused default
memory plugin is now disabled. Only the new Slack service is installed or
restarted during activation.

The original v1 Slack Gateway ran with isolated
state and the existing subscription credential refresh owner. It exposed only
`jumpserve_status` and `jumpserve_request`. Every channel member can request work;
new tasks use the current database category budget and existing qualified release
path. Queued tasks appear in Platform Updates. Global owner controls retain their
existing checks. Shared status excludes private owner DM tasks and unrelated
private task details.

Original model requests, streams and outcome receipts are retained in private
Supabase Storage with immutable database indexes. Persistence settlement never
repeats a completed model call. Truly uncertain calls retain their fence across
service restarts. Recurring chat heartbeats, unsolicited introductions, presence
greetings, generated shell tools and automatic framework updates are disabled.

The deployed v1's local verification included 122 database checks, 14 Python
checks, two tool transport tests, and the pinned native configuration/plugin checks. Production
conversation checks are recorded below.

`python3 -B bin/platform-slack.py prepare` freezes the qualified source bundle and
release packet under `.test-artifacts/slack-setup-v1/qualification/`. It starts
no Gateway and makes no model calls. The `verify` action checks the stored
credentials without printing tokens or temporary websocket URLs.

## Production deployment and evidence

The owner explicitly requested production deployment on 2026-11-04. Migration
`202611040001_platform_slack_gateway.sql` is applied to the fixed JumpServe
project `regphejnlvfpyokpniny`. Its function hashes, RLS and service-only RPC
permissions were verified. Existing platform and research control functions
remain unchanged. The enabled Slack binding delegates through the existing,
verified Google owner; it does not derive an identity from the standing
authority's nullable `authorized_by` field.

The qualified bundle is
`976772d105e50ab57844125b499fea22ba35028e73629f64c99ecd4088caae05`.
It is installed on `i-087f1493809643115` as
`jumpserve-platform-slack.service`. Native validation succeeded before activation
(SSM `3a9f42d3-4048-4680-99b5-9007d13d1d7c`), followed by installation
(`2b6fd8df-1d88-4370-b341-0d8a09b7ce99`). Socket Mode connected at
18:36:20 UTC. Initial configuration recovery and the 1-GiB startup OOM were fixed
before the first live message: configuration now uses the official native writer
and validates its readback metadata.

Live checks used read-only requests:

- [Channel mention and threaded follow-up](https://dnagroupworld.slack.com/archives/C0CEXNJE0HX/p1793817424703179):
  the reply used `jumpserve_status`, reported live database health/counts and
  distinguished polling from successful repairs. A follow-up without another
  mention received a reply in the same thread.
- The owner's separate DM received its own live status reply and reported zero
  tasks shared in that DM. Private DM contents are not copied to this document
  or the group channel.
- The first five model calls all completed, with original request/response/outcome
  records verified in private Supabase Storage/database indexes. No work requests
  were queued by these tests.
- A controlled service restart (SSM `51e1f2dc-544f-4b8e-b2d6-fc39ca30a204`)
  preserved all five call identities and both existing workers' process IDs.
  Socket Mode reconnected at 18:40:53 UTC using the instance role and existing
  secret, without interactive AWS sign-in.

All-human channel access, removed-member rejection, unlisted-channel denial,
owner-only DMs and private task projections also pass the local transport and
database checks. The live channel test used the owner; another human's identity
was not impersonated or claimed as a separate live test. No claim of unattended
research completion follows from these chat checks.

For subsequent releases, obtain the current deployment instruction required by
`AGENTS.md`, freeze the qualified source with `prepare`, upload the exact bundle
under the existing asset bucket's `platform-supervisor/slack/` prefix, and use the
fixed-host installer first for validation and then `--activate`. Verify the bundle
hash before running its root-owned bootstrap. Preserve applied migrations and
all original call/state records, including uncertain-call fences. Verify actual
Slack replies and retained receipts after activation; service activity alone is
insufficient. For v2 apply **all** migrations listed in the release packet before
activation, including the new controls migration. A v1-only migration runner is
insufficient; the installer deliberately rejects the missing v2 contract.

Socket Mode uses an outbound connection from AWS and needs no public Gateway
port. Run the qualified Gateway under systemd on AWS; the user's computer must
not own the listener or be needed to keep it available.

Official references: [OpenClaw Slack setup](https://github.com/openclaw/openclaw/blob/v2026.10.5/docs/channels/slack/setup.md),
[Slack access control](https://github.com/openclaw/openclaw/blob/v2026.10.5/docs/channels/slack/access-control.md),
[Slack Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/).
