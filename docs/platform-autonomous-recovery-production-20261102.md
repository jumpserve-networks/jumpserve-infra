# Persistent incident and operational supervisor self-repair release — 2026-11-02

The user explicitly requested this production deployment. The interactive release
is recorded separately from subsequent autonomous supervisor work.

## Released source and verification

- Backend PR [29](https://github.com/jumpserve-networks/jumpserve-back-end/pull/29),
  revision `04d9303b87797eddaa4cd0abb41ca2d9fea86073`.
- Infrastructure PR [55](https://github.com/jumpserve-networks/jumpserve-infra/pull/55),
  followed by permission-hardening PR [56](https://github.com/jumpserve-networks/jumpserve-infra/pull/56).
  Activated infrastructure revision: `37be581fc6b056b0b391d1299a602e8e1edb8ba9`.
- Bundle SHA-256:
  `11a18d0f01dc165d8b0430b378b17afac15c34a6b08136f0b087dc2faa581c17`.
- Release operation: `81b1fbb8-48fa-4197-99b2-e680961ddbab`.
- Production receipt event: `3223a002-9eae-5cdd-8c95-79dc5bf74146`.

Administrator-enforced branch protection and exact `Platform validation` checks
passed at both activated revisions. Local checks passed 105 supervisor tests,
514 research workflow tests, 43 release-broker tests, 118 database checks,
100 infrastructure Jest checks and the TypeScript build. Five existing optional
Jest checks remained skipped. The exact candidate also passed all 105 supervisor
tests on the existing AWS host with synthetic provider transport and no provider
calls. All 31 bundle files matched deterministic local packaging.

The access-stack update changed only the release role's scoped Supabase-secret
and SSM permissions, plus generated CDK metadata. The deployed template matched
the reviewed candidate. No host replacement, new static credential or research
runtime release was performed.

## Database and installation

Platform admissions paused while existing supervisor leases and actions drained.
The release applied migrations `202611020002_platform_incident_continuations.sql`,
`202611020003_supervisor_self_install.sql` and
`202611020004_private_incident_continuation_context.sql`.

Production readback found that the newly created context helper inherited
database-specific execution grants. The forward hardening migration immediately
revoked browser and direct-service execution while admissions remained paused,
before the service switch. A new regression verified denial through all three
roles, positive retrieval through the valid leased RPC and stale-token denial.
This record does not claim a forensic finding about access during that interval.

All 51 inspected function bodies and security settings matched the qualified
database. Existing access differences on the immutable trigger and operator
predicate were recorded and preserved; their bodies were unchanged. The context
helper is private, and its checked service entry point remains available.

One original SSM installation command switched the versioned supervisor symlink.
It verified predecessor bytes, installed bytes, both active services and unchanged
research runtime files, with the prior release retained for rollback. Separate
readback verified the actual running process's source directory, all 31 installed
files, the unchanged service environment and IAM-role credential method. All 71
research-runtime files still matched runtime 86.

Two unsuccessful read-only verification probes remain retained: one assumed the
source path appeared in systemd's command instead of `WorkingDirectory`; its
correction initially had an indentation error. The final probe verified the
configured command, working directory and actual process directory. The original
installation was successful and was not repeated.

The initial self-update baseline was recorded only after separate exact-source
host readback and protected backend checks. A subsequent call through the actual
installed service client retrieved the identical private runtime manifest.
Admission resumed with automatic releases enabled at settings revision 58.
Original assessment deadlines, category budgets and the retained original HTTP
503 record remained unchanged.

Qualification and production receipts were uploaded to private Supabase Storage
and read back. Qualification archive SHA-256:
`6f36edd60747b2754f86d0a536940a24edfd90dd1ceefe233048636e13f6f198`.
Production verification archive SHA-256:
`49c848e55536dba7da577a250a0776b09b7eaca476c9c62e729d9703a35b925c`.
Operator-visible events and subsequent task progress are available in
[Platform Updates](https://jumpserve.quaint-lab.org/platform-updates).

## Observed autonomous continuation and limits

At `2026-11-02T20:11:06.807762Z`, ordinary maintenance admitted the first follow-up
for assessment `fe761052-6e57-4d47-a3de-163c6cad905b`; six follow-ups were admitted
for six distinct unresolved claim tasks. No operator manually queued them.
The service claimed task `7a6141a5-f55b-4263-8197-dfb470aaeada` at
`2026-11-02T20:11:07.658770Z` and subsequently reported `working`.
That task carried its predecessor's 20 model reservations and 2,000 cents rather
than resetting usage. Its new six-hour operational window remains bounded by the
unchanged assessment deadline.

This proves live follow-up admission and installed capability. It does not yet
prove an autonomous self-update or successful repair of those assessment
blockers. At the first post-activation observation, research still had one
complete and twelve partial runs, with the latest run at
`2026-11-02T02:55:29.649950Z`. Assessment recovery and new measurements require
their own original evidence. Full unattended paper reproduction remains unproven.
