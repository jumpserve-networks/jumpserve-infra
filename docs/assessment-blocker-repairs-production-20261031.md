# Assessment blocker repair activation, 2026-10-31

The user explicitly requested production deployment of the prepared blocker-driven
repair change. This was an operator-requested interactive deployment. Subsequent
repair task execution belongs to the separate AWS platform supervisor.

## Released source and activation

- Infrastructure [PR #25](https://github.com/jumpserve-networks/jumpserve-infra/pull/25),
  tested head `401e8f7918b58eb155f9d6dad111e211b29f18b2`, merged revision
  `64a259235bb6b03420be04f8976b39accf6851c0`.
- Required [Platform validation](https://github.com/jumpserve-networks/jumpserve-infra/actions/runs/41223777765)
  and [infrastructure validation](https://github.com/jumpserve-networks/jumpserve-infra/actions/runs/41223777650)
  both passed. Local checks included 65 PostgreSQL checks and 12 release/bootstrap
  checks. All seven reviewed source file hashes matched the merged revision.
- Applied only `database/202610310002_assessment_blocker_repairs.sql` to JumpServe
  Supabase project `regphejnlvfpyokpniny`. Migration SHA-256:
  `d81a8aa6f6b073100f3e8286a9e6130b4d258acc9b55af93df6c32a071f92dc0`.
- Activation committed at `2026-10-31T17:19:37.378150Z`. The transactional private
  Platform Updates event is `55916da5-8e7a-5e59-87ea-bf30d7b70e69`.
- The read-back verification event is `98362c8d-c6fe-5310-a779-fd2f63d3e899`,
  retaining the `2026-10-31T17:21:31.551537Z` observation.

The fixed-project administrative connection was used because the connected
Supabase MCP pointed to a different project. No query or mutation was sent to
that other project. Activation did not reinstall/restart the AWS worker, change
IAM, deploy application stacks, change runtime pins, reenroll operators or alter
the standing `platform-supervisor-v1.1` model policy.

## Observed production behavior

Activation captured 39 retained blocker signals. The existing AWS service admitted
eight priority-zero repair tasks at approximately `17:19:45Z` and claimed its first
repair at `17:19:45.999043Z`, about nine seconds after activation. At the recorded
verification, 31 signals remained pending later safe admission. The daily general
maintenance admission was still `2026-10-31T02:40:58.663989Z`; the new repair path
therefore ran before the daily slot became eligible again.

Two admitted tasks cover the public paper assessment
`444d171c-2fac-4ba9-b33c-2b46304cb0ec`: `6524dea3-7ceb-43c4-be0c-627f27b5112a`
and `7de51698-64c3-4d38-a405-f506bc39b4bf`. They were queued at this snapshot.
Other private assessment identities and diagnostics are retained in the protected
dashboard and are not included here.

The actual installed function sources matched the reviewed migration. The
predecessor platform worker, operator controls and research dispatch/host guards
retained their original sources. All three new relations had RLS and denied
anonymous/browser SQL reads and service-role inserts/updates. All three capture
triggers existed. Only the service role could invoke the new worker RPC; runtime
roles could not invoke the legacy worker or forge capture calls. Active assessment
spending limits, attempt limits and deadlines matched their preflight snapshots.
The supervisor remained unpaused with automatic releases enabled and a fresh
heartbeat. Private activation, capture and queue events are exposed through
[Platform Updates](https://jumpserve.quaint-lab.org/platform-updates).

## Verification limits

These receipts prove deployed event capture, guarded task admission and actual AWS
worker pickup. They do not prove a successful code correction, production release
of such a correction, or resumed/completed scientific assessment. Those outcomes
need their separate original action identities and exact verification receipts.
The worker processes one platform task at a time and retains existing research
host priority. In-flight work and unavailable shared capacity can delay further
admission/execution. Protected worker/runtime/database changes still require their
dedicated qualification paths. Daily housekeeping remains separate.

Private local evidence is retained under
`.test-artifacts/assessment-blocker-repairs-v1/`, including reviewed hashes,
preflight, source merge receipt, activation intent/acknowledgement, installed
function/ACL checks, observed task links and the read-back verification event.
