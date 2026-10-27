# OpenClaw grant recovery: local candidate

This change implements the requested refresh/storage reliability improvements.
It remains local and uncommitted. No merge, push, production status polling,
credential inspection, AWS change or deployment is authorized by this editing
turn. The runtime manifest is candidate version 40, with 35 exact file hashes
and an explicit uncommitted-revision marker. Its source revision is the base,
not a claim that those modified bytes are already committed or deployed.

The backend protocol is
`../jumpserve-back-end/research_workflow/auth-recovery-protocol-v1.md`. Native
OpenClaw 2026.10.5, Node 24.16.0, the existing host-specific ChatGPT grant, model
and published prompt remain the declared configuration. No API-key fallback is
introduced. No new tables, grants, SQL migration, browser interface or public
status shape is needed. Private `research_model_workers.configuration` stores
safe reason/cooldown metadata through the existing heartbeat RPC. Pre-provider
failures preserve the original logical request and a terminal dispatch receipt,
with known zero provider calls and missing usage/costs kept missing.

The helper records and flushes a replacement in a bounded, preallocated private
recovery slot before committing native SQLite state. Existing host refresh
locking and a SQLite write transaction prevent cooperating refresh owners from
rotating the same grant concurrently. Pending intent without a durable result
is an uncertain rotation, not evidence that a token expired. The stored grant,
client/account identity and recovery slots never enter research artifact uploads,
browser data or diagnostics. All private files remain on the protected encrypted
worker storage. This does not create a separate auth volume; low-space admission
and recovery protect the existing arrangement without replacing the host.

Two operational bypasses were also removed locally. `host-check` now uses the
same locked credential owner rather than invoking a separate refresh first.
`host-refresh` uses the recovery-aware owner, including its identity, journal and
backoff checks. Native interactive/background login requires held admission and
polling, drained active/recent uncertain calls, a stopped worker during login,
and the same private lock. Its shell restores the prior service state even if
login fails. The helper refuses maintenance without those conditions. It must
not stop or restart an active scientific model call just to obtain a new grant.

These failure mechanisms can explain unnecessary sign-in requests, but the local
tests do not establish the historical cause of the earlier production
`invalid_grant`. Invalid or revoked grants still require reconnection. Never
recover an uncertain model outcome by resetting or resubmitting its dispatch ID.

For a later explicitly requested release:

1. Commit reviewed backend changes and pin their exact revision in the candidate
   manifest. Stage and verify all 35 files. Retain the prior revision/bytes and
   current worker/auth state; do not replace the instance or its bootstrap asset.
2. Verify AWS account 395567831870 and Supabase project regphejnlvfpyokpniny before
   any live changes. Hold new admission/polling and drain active model work.
   Preserve historical unknown outcomes. If the legacy worker is quota-paused,
   explicitly carry that hold into the new private availability state before
   restarting; the old implementation held it only in memory.
3. Update the exact Lambda/worker runtime asset through the scoped release path.
   No database or frontend release is required. Never run native authorization
   concurrently with another refresher; the maintenance helper enforces the hold,
   drain, stopped service and shared lock for supported login commands.
4. Check pinned host source/runtime bytes and the worker's own native grant
   through the locked owner. A real expiry/refresh/reconnect and authenticated
   queue recovery remain conditional release checks. Avoid needless forced
   refreshes or consuming model allowance merely to test a status badge.
5. Verify private diagnostics, queued identity preservation, quota behavior and
   public status projection before restoring admission. A successful local fake
   provider response is not production authorization verification.

Local test coverage includes actual temporary SQLite/filesystem operations,
abrupt child-process exit after recovery fsync, two separate Python processes
sharing one refresh lock, and the real native CLI with a loopback fake provider.
ENOSPC/commit failure and network/provider errors are injected development cases,
not a physical power-loss, real full XFS-volume or live OpenAI campaign. The AI
implementer is the evaluator/reviewer; no human or independent review is claimed.
The accompanying JSON report retains exact checks, hashes, limits and gaps.

Primary documentation:

- [OpenAI token lifetimes](https://developers.openai.com/siwc/token-sharing-open-source/token-reference#token-lifetimes)
- [Account persistence and serialized refresh](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions#refreshing-tokens)
- [Refresh error recovery](https://developers.openai.com/siwc/token-sharing-open-source/errors-and-recovery#refresh-errors)
- [Node SQLite](https://nodejs.org/docs/latest-v24.x/api/sqlite.html) and
  [filesystem synchronization](https://nodejs.org/docs/latest-v24.x/api/fs.html)
