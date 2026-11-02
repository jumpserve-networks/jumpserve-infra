# Supervisor reconciliation production release — 2026-11-02

The user explicitly requested this production deployment. It is an interactive
release, separately identified from autonomous supervisor accomplishments.

## Released source and verification

- Backend PR [28](https://github.com/jumpserve-networks/jumpserve-back-end/pull/28),
  merged revision `b378290e3c45d3aa13e71474c8400acd37ca04ed`.
- Infrastructure PR [53](https://github.com/jumpserve-networks/jumpserve-infra/pull/53),
  merged revision `10e6b32f9bec8ad7eca726eebd28fbb9dff78e34`.
- Supervisor bundle SHA-256:
  `cdbf2ac8d8b8d8f1e575df3b1e88e2472ca349df8f6d637ace69b96d17d476e0`.
- Migration: `202611020001_platform_reconciliation_progress.sql`.
- Release operation: `0e5cebab-f3ac-4baf-a015-4175d8a04b9c`.
- Production receipt event: `b4847818-0eec-5a31-a616-4f44dd998764`.
- Live recovery event: `d2d8128d-0429-55a3-886c-d0187180e39c`.

Administrator-enforced branch protection and `Platform validation` passed at
both merged revisions. Local verification passed 92 supervisor tests, 103
database checks, 37 release tests and 514 research tests. The exact candidate
also passed all 92 supervisor tests on the existing AWS host with synthetic
provider transport and no qualification model calls. The original 93 database
regressions remain included in the 103-check suite.

Platform admission paused while existing supervisor work drained. The migration
was applied before the service switch. All three affected function bodies and
their security settings matched the tested database definitions; the worker RPC
remained service-only and its predecessor helper remained private.

Readback verified all 27 installed bundle files, the service executable and
active supervisor/research services. All 71 research-runtime files still matched
runtime 86. The worker's AWS credential method was `iam-role`. No frontend build,
new host, research-runtime release or credential replacement was needed. The
previous versioned supervisor release remains available for rollback.

The release preserved original model records, task/assessment deadlines and
category budgets. Admission resumed with automatic releases enabled at settings
revision 56. Qualification logs and the production verification receipt were
uploaded to private Supabase Storage and read back; the qualification archive's
SHA-256 is `50dd376919fc4d8370bb31a5bd091bca0bc22958b360eea9ccd1bf13c226a825`.
Operator-visible records are available in
[Platform Updates](https://jumpserve.quaint-lab.org/platform-updates).

## Observed recovery and limits

At `2026-11-02T17:22:09.932029Z`, the newly installed supervisor automatically
appended a `platform-native-http-reconciliation-v1` proof for original native
call `0f09c104-0827-4be8-a419-b691f57854b2`. Its retained HTTP 503 received the
supplemental outcome `failed`, without replaying its request or changing the
original `unknown` row. The proof retained the original request, response and
receipt references; processing and charges at the provider remain unknown.

Task `910739f6-118c-47ea-ab3e-ddd70b8efe34` then released its host turn and reached
`deadline` under its original `2026-11-02T08:12:29.24388Z` deadline. It can no
longer monopolize turns by repeatedly reconciling that HTTP 503. No replacement
deadline or model call was granted to the expired task. The assessment workflow
remained running, and fresh supervisor heartbeats continued after admission
resumed.

This verifies the specific live HTTP recovery path. Concurrent independent-task
rotation, backoff and shared-host safeguards passed the database and supervisor
regressions. Passing qualification or reconciling this call does not establish
that other uncertain calls are resolved, that a new repair has completed, or
that paper experiments have reached 100% unattended completion. Track those
outcomes through their own original evidence and measurements.
