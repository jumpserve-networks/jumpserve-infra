# Planner handoff production release

Release status: pending Linux qualification and deployment. The final receipt is
`autonomy-completion-production-v1-status.json`; this report is updated after
deployed verification. Scientific assessment progress is separate.

The release replaces duplicate native context with a hash-bound handoff while
preserving the complete original upstream policy, messages and decision schema.
It retains exact transports, request sizes, structured validation failures and
safe public reasons. Original 96 KB limits, no paid fallback, unknown-call fences,
paper budget/deadline and historical records are preserved. Published prompt
templates and scientific decision rules are unchanged.

The local evidence is described in `autonomy-completion-local-v1.md`: 396 passing
backend tests, the exact retained-request comparison, two complete isolated
PDF-to-assessment campaigns with synthetic judgments, and actual local TCP and
Linux netem measurements. These are exposed development checks, not unseen-paper
performance or complete production validation.

The frozen release protocol is `autonomy-completion-release-protocol-v1.json`.
The existing production Linux worker checks the same retained request against
old/new source, all native transport/safety regressions, and one actual bounded
ChatGPT subscription response. This live response is an explicit missing-source
software fixture; it does not measure a paper claim. Unchanged builder and netem
qualification is inherited only after file hashes and shared-function ASTs match.
The exact-source repair approval is renewed only after inspection and persistence
of the new qualification evidence. No human or independent review is claimed.

Deployment updates the existing worker and research Lambda assets with admissions
held. The worker's encrypted 300 GiB disk, installed image and grant are preserved.
Deployed source hashes, RLS/browser-write denial, executor assets and public API
checks precede reactivation. No frontend or database migration is planned.

The original assessment remains
`4055396e-35c0-4962-ba39-cf23e443ad8d`, with a $1,000 ceiling, its original
November 4 deadline and no AI-turn cap. Observe actual post-release job and
measurement progress without resetting these limits, changing criteria or
replaying uncertain dispatches. The ten-minute release observation window is
separate from the paper's ongoing campaign limits. Unresolved claims and absence
of queued measurements remain explicit verification gaps.

Release-controller failures are retained too: an expired AWS session prevented
one freeze before any qualification call; a local prerequisite initially looked
for a worker-only phase file before archive collection; a status collector
initially assumed every case supplied a status. Corrected collection uses the
original worker phase snapshot and preserves missing case status as missing.
These corrections do not replay inference or relax host pass criteria.
The first Linux native suite ran 14 tests with one fixture error: its oversized
serializer replacement was applied before building the otherwise valid logical
request, so production OPENCLAW mode rejected it at the earlier controller guard.
The failed native log and evaluation remain retained. A separate follow-up builds
the admitted input first and asserts controller and runtime limits independently;
the runtime source is byte-identical and all 14 tests with zero skips remain
required. The earlier failure consumed zero live provider calls.

Reproduction and scoped release commands, from `jumpserve-infra`:

```sh
python3 -B bin/autonomy-completion-release.py freeze
python3 -B bin/autonomy-completion-release.py prepare
python3 -B bin/autonomy-completion-release.py status
python3 -B bin/autonomy-completion-release.py native
python3 -B bin/autonomy-completion-release.py status
python3 -B bin/autonomy-completion-release.py live
python3 -B bin/autonomy-completion-release.py status
python3 -B bin/autonomy-completion-release.py evidence
python3 -B bin/autonomy-completion-release.py status
python3 -B bin/autonomy-completion-release.py collect
```

Each dispatched phase runs once; inspect its original command and retrieve its
results. `record-review` requires the implementing AI's actual-answer inspection;
`approve` binds exact nonapproval file hashes to the retained evidence. Commit
the policy, `pin`, stage with `bin/prepare-research-runtime.py`, run infrastructure
tests/build, and review scoped `bin/openclaw-release.py` diffs before deployment.
Verify held/active bytes and executors before calling `record-release` to append
the hash-verified private release artifact. Authentication-dependent browser
checks are reported as conditional when a legitimate session is unavailable.

Reservation ceilings are conservative commitments, not invoices. Available
actual model usage is retained; subscription allocation and unallocated
host/storage charges remain unknown. No new cloud worker is needed.
