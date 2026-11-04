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
loads both supervisor tools, and the official Slack plugin installation passes
the version, integrity and trusted-install checks.

## Verified credentials and prepared gateway

Both credentials are stored in the dedicated AWS secret
`jumpserve/platform-supervisor-slack`, account `395567831870`, region `us-east-1`.
The app-level token has `connections:write`. Slack accepted both credentials,
confirmed the bot's workspace and app identity, and confirmed membership in
`C0CEXNJE0HX`. Neither credential is in source, CLI arguments or evidence files.

A read-only SSM preflight confirmed that the existing host's **instance role**
can read the secret, and that its Node/OpenClaw versions match. The existing
service policy already covers this secret; no additional IAM grant was needed.
The 1-GiB service memory limit leaves headroom for the existing workers. Only
the new Slack service is installed or restarted during activation.

`assets/platform/slack_gateway.py` runs the native Slack Gateway with isolated
state and the existing subscription credential refresh owner. It exposes only
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

Local verification includes 122 database checks, 13 Python checks, two tool
transport tests, and the pinned native configuration/plugin checks. These are
local qualifications; a production Slack conversation has **not** been verified.

`python3 -B bin/platform-slack.py prepare` freezes the qualified source bundle and
release packet under `.test-artifacts/slack-setup-v1/qualification/`. It starts
no Gateway and makes no model calls. The `verify` action checks the stored
credentials without printing tokens or temporary websocket URLs.

## Activation still required

**The app is installed, but the AWS chat Gateway is not running.** Its migration
has not been applied and its source changes remain local. The existing platform
supervisor continues using its existing isolated coding sessions.

1. Obtain the new explicit deployment instruction required by `AGENTS.md` for
   these interactive source changes; app installation approval is already given.
2. Apply `database/202611040001_platform_slack_gateway.sql`. It creates only new
   private relations and service-only adapters. Bind the fixed team/channel/DM
   owner to the existing Google owner verified in the private release packet;
   never invent a Google JWT. The current standing authority's `authorized_by`
   can be null, so it is not an implicit Slack identity link.
3. Upload the exact qualified bundle under the existing asset bucket's
   `platform-supervisor/slack/` prefix. Use the fixed-host installer on
   `i-087f1493809643115`, first for native validation and then activation. Verify
   the bundle hash before executing its root-owned bootstrap copy. The installer
   verifies frozen source and official plugin integrity before starting systemd.
4. Verify an actual human mention, a threaded follow-up, owner DM isolation,
   second-member access, unlisted-channel denial, tool receipts and a service
   restart on AWS. Retain original evidence and roll back the Slack service if
   qualification fails; do not claim operational success from `is-active` alone.

Socket Mode uses an outbound connection from AWS and needs no public Gateway
port. Run the qualified Gateway under systemd on AWS; the user's computer must
not own the listener or be needed to keep it available.

Official references: [OpenClaw Slack setup](https://github.com/openclaw/openclaw/blob/v2026.10.5/docs/channels/slack/setup.md),
[Slack access control](https://github.com/openclaw/openclaw/blob/v2026.10.5/docs/channels/slack/access-control.md),
[Slack Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/).
