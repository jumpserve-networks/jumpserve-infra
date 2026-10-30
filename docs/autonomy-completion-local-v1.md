# Local planner correction and unattended integration verification

The remaining planning failure now has a reproducible local mechanism and a
corrected implementation. Changes are local and uncommitted. No application,
infrastructure or prompt was deployed or published in this work.

## Retained incident and controlled comparison

The source is failed production dispatch
`6e5b884a-3322-508b-ae00-c01df7ec9307` in assessment
`4055396e-35c0-4962-ba39-cf23e443ad8d`. Its receipt records
`local-pre-provider-ValueError`, zero provider calls and no provider request sent.
Original logical request, message, receipt and native stdout/stderr were retrieved
and hash verified. The original receipt does not identify a precise boundary or
the production bridge-body size; that missing observability is preserved.

Using the exact retained logical request and the pinned native OpenClaw CLI
locally, backend `52abe168691afb678ecfcbd91f3f07b70fb7ca04` reproduces failure:

| Transport | Original implementation | Corrected implementation |
| --- | ---: | ---: |
| Complete logical request | 94,258 bytes | 94,258 bytes |
| Local native wrapper/body | 102,035 bytes | 28,153 bytes |
| Complete intended provider request | 94,564 bytes | 94,564 bytes |
| Bridge admission bound | 96,000 bytes | 96,000 bytes |
| Actual upstream calls in this control | 0 | 1 synthetic response |

The corrected upstream request is checked byte for byte against the unchanged
conversion of the original logical request (SHA256
`8f4e70f5358dce16d077fcb3dd83771c73cc08400815b89a424972818b155511`).
The local mechanism is consistent with the retained production failure; exact
production byte counts require the new diagnostics after deployment.
The final matched comparison captures the runtime source before execution and
asserts unchanged bytes after each case. Earlier comparisons remain separate.

Native OpenClaw now receives a short handoff containing the original request's
SHA256. The original context remains in `logical.json` and `message.json`; the
local bridge sends the complete original policy, messages and decision schema
upstream unchanged. No context, scientific criterion or source evidence is
silently truncated. The bridge verifies the handoff identity and still rejects
tools, wrong models/roles, malformed bodies and oversized requests.

Versioned receipts record sizes at the logical, native and upstream boundaries,
plus safe validation codes, fields and bounds. Known zero-call failures produce
precise queue reasons without echoing source text, prompts or credentials. An
uncertain earlier provider outcome remains fenced and is not overwritten by a
subsequent rejected request. Existing request bounds, paid-fallback prohibition,
original paper budget/deadline and dispatch identities remain intact.

## Full local assessment flow

Two campaigns passed, with every model decision explicitly synthetic. The final
campaign takes a generated PDF through the real upload/extraction/organization
and confirmation functions. After its single scope confirmation, the ordinary
controller runs to terminal `completed` without manual campaign edits.

The final campaign retained:

- 2 numerical software-fixture claims and their distinct frozen criteria.
- 10 numbered controller turns, native CLI calls and durable model dispatches,
  with original prompts, native/provider bytes and outbox persistence.
- 1 shared TCP experiment job, 1 complete run and 1 experiment commitment.
- 2 actual local TCP exchanges and 4 recorded measurements: two received-byte
  values (32 bytes each) and two measured round-trip times in milliseconds.
- 1 `reproduced` and 1 `discrepant` fixture assessment using the original 32-byte
  and 33-byte criteria. No favorable-result reacquisition or criterion changes.
- 117 artifacts checked by retrieval, byte count and original SHA256.
- Unchanged authorization, initial prompt/hash, claims and elapsed-time limit.

The two claims share an acquisition but retain separate protocols and judgments.
The queue job remains `awaiting-review`: the claim assessments are recorded by the
autonomous controller, while that separate queue publication/review state is not
silently rewritten. Both the workflow terminal state and scientific-label
calculations are checked explicitly.

The native CLI, PDF parser, Postgres RPCs, worker, actual TCP exchanges, evidence
calculation and artifact hash checks use real implementations. Google identity,
Storage transport, wake notifications, Lambda SDK transport and all model
judgments are fixtures. In particular, these are not live AI planning reviews,
deployed cloud execution, public browser authentication or assessments of the
retained fictional CUBIC manuscript. No live inference was requested. Token
counts in synthetic replies are labelled fixture data and are not measured model
usage or billing.

Separately, the existing isolated Linux namespace/netem smoke check passed with
10 recorded observations over its two declared conditions, receiver byte/time
conservation checks and an unloaded RTT control. It is not the paper's full
30-second loss sweep or an independent-host replication.

396 backend tests passed after the final change. New regressions cover the exact
native handoff, unchanged provider content, rejected fields and byte bounds,
zero-call receipts, safe public error messages, and fencing of uncertain calls.
Failed socket/Postgres attempts in the restricted sandbox remain retained; their
subsequent scoped local checks are separate runs.

## Reproduce and remaining verification

From `jumpserve-back-end`:

```sh
python3 -B -m unittest discover -s research_workflow/tests
python3 -B research_workflow/tests/check_netem_iperf_linux.py
```

From `jumpserve-infra`:

```sh
python3 -B bin/check-autonomy-planner-local.py compare
npm run test:research:completion
```

The matched native comparison requires its hash-verified private incident bytes
and the retained OpenClaw/Node installation. The integration requires the local
Postgres fixture service, PDF parser and native CLI. Linux checks require the
preinstalled Docker image. Protocols and failed/successful reports are retained
under `.test-artifacts/autonomy-completion-v1` and the database fixture directories.
The first private evidence archive remains retained as SHA256
`8fdb4dcb3b2bfb87aa12d67e49435c8d6525b5041188b9b53dc23f0b27b9b361`.
The final source-locked follow-up is appended separately; its current artifact
identity and verified hash are in `autonomy-completion-local-v1-status.json`.
No confidence interval or unseen-paper performance claim is supported by these
exposed deterministic development cases. Reviewer: implementing Codex AI; not
human, independent or held out. Measured host/storage charges are unavailable.

The next production check, after an explicit deployment request, is to verify the
same source on the Linux worker and observe the original assessment producing
queue jobs, ingested measurements and justified decisions within its remaining
budget and deadline. Authenticated browser upload/confirmation and live model
answer quality also remain conditional checks. Passing this local integration
does not establish universal unattended autonomy across research papers.
