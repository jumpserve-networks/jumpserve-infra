# Planner handoff production release

Release status: deployed and active. Backend `5c9525d92938a53aa39f078795f99a9bc0a87cd6`
is pinned by runtime manifest 72 (59 files). The worker runtime update completed
at 02:57:50 UTC on October 30, 2026, the research-function deployment at 03:00:31,
and activation at 03:02:38. Deployed active-source verification passed at 03:03.
The final receipt is `autonomy-completion-production-v1-status.json`.
Scientific assessment progress is separate.

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

The follow-up Linux qualification passed all 14 native tests without skips.
For the exact retained request, the old native bridge was 101,520 bytes and
failed before an upstream call. The corrected bridge was 27,638 bytes while
the complete 94,564-byte upstream request retained SHA-256
`8f4e70f5358dce16d077fcb3dd83771c73cc08400815b89a424972818b155511`.
The one actual subscription call completed in 28.99 seconds, using 3,608 input
and 91 output tokens. Its actual answer was examined: it returned a missing-data
blocker with no claims, evidence, proposal or assessment label, and incomplete
coverage, as required by the explicit missing-source fixture. No provider retry
or paid fallback occurred. The implementing AI recorded a passing evaluation
(`66826224dae6c5f149d2dac75be232816874fb48017286b4960d86fa75e4bf29`)
against both existing published prompts; prompt publication did not change.
The private qualification archive was retrieved and hash-verified as
`0f165f7a5b37e0c34dc930832b24f548276bdfccbea0e9b910f4336b81f34337`.

Final infrastructure validation passed 94 tests; five CLI contract cases were
initially skipped without `JUMPSERVE_BACKEND_CHECKOUT`, then all five passed in
a separate invocation with the actual backend checkout. TypeScript compilation
passed. These additional CLI checks import parsers and do not launch networks.

Deployment updated the existing worker and research Lambda assets with admissions
held. The worker's encrypted 300 GiB disk, installed image and grant were preserved.
The API, queue, autonomy worker and existing host passed exact 59-file checks and
RLS/browser-write denial checks before reactivation. Executor, ingest and reaper
ZIPs also matched all 59 files. Active-source verification then checked ready
worker health, enabled polling/admission, unchanged $100/7-day defaults and no
AI-turn cap. Four public provenance/status reads returned 200; two unauthenticated
write attempts returned 401. The active benchmark image and literal stack
parameters remained unchanged. No frontend or database migration was needed.

Native Firefox inspection verified the live public queue on desktop and a
390-by-844 mobile viewport. The held-controller warning disappeared, independent
claim progress updated, and the recorded prompt/response details opened while
signed out. The empty-job state and honest untested labels remained visible.
Desktop mode was restored. Fresh authenticated Google login, PDF upload,
confirmation and chat were not re-exercised because this browser had no legitimate
JumpServe session. Unchanged chart/export/theme and sign-in-return behavior was
not newly tested. The overall workflow reason still showed a historical
all-tasks-recorded-outcome message while individual tasks were running; use the
individual statuses and timestamps to interpret resumption. This is a recorded
display limitation, not evidence of paper completion.

The original assessment remains
`4055396e-35c0-4962-ba39-cf23e443ad8d`, with a $1,000 ceiling, its original
November 4 deadline and no AI-turn cap. Observe actual post-release job and
measurement progress without resetting these limits, changing criteria or
replaying uncertain dispatches. The ten-minute release observation window is
separate from the paper's ongoing campaign limits. Unresolved claims and absence
of queued measurements remain explicit verification gaps.

The first two completed post-release dispatches were retained as
`457c979a-a271-51b6-9de0-56335166876c` and
`534a7aa5-d06a-5846-825e-22cab11f52cc`. Their actual receipt/stdout/stderr bytes were
retrieved and hash-verified. They completed seven and six builder provider calls,
respectively, then retained recoverable native-context checkpoints and working
source files. A checkpoint is not an executable package or a scientific result.
The first native CLI stdout reported its controlled next-call context rejection;
the application receipt identified that unadmitted next call and preserved the
completed calls and checkpoint. Do not interpret the receipt's `complete` status
as completion of the entire experiment. No manual model replay, package editing,
assessment reset or label change was performed by these observations.
The later bounded observation at 03:09:43 retrieved six completed outcomes:
three admitted after activation and three older records. The three new slices
reported 20 completed builder calls in total and retained checkpoints; this is
separate from the one release qualification call. It is not a complete inventory
of background usage. At 03:10:58 the assessment had two building tasks running,
two queued, one waiting for reconciliation, five untested labels and zero jobs.
Commitments were $763.65 of $1,000; this is not measured spend. Its deadline,
maximum and original initial-prompt hash were unchanged. These observations do
not validate unattended completion of this paper; package completion and real
experiment ingestion remain unverified for this assessment.

Release-controller failures are retained too: an expired AWS session prevented
one freeze before any qualification call; a local prerequisite initially looked
for a worker-only phase file before archive collection; a status collector
initially assumed every case supplied a status. Corrected collection uses the
original worker phase snapshot and preserves missing case status as missing.
These corrections do not replay inference or relax host pass criteria.
After activation, simultaneous read-only checks exposed a microsecond-based
local report-directory collision. The snapshot failed before target checks or
database access. New report directories include a random suffix; repeating only
that read-only snapshot succeeded. Its original failure is retained with the
release evidence and does not alter any qualification phase or production data.
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
