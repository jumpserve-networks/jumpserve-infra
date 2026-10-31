# Autonomous repair, reconciliation and measurement persistence

Implemented and verified locally on October 30, 2026. Production runtime,
published prompts and the original paper assessment were not changed. This is
development qualification, not proof of universal autonomy or a paper finding.

Implementation repair keeps its original incident, source baseline and checkpoint
and enters the native builder. The working packet now supplies the exact JSON
test-plan object, required tests, accepted paths and current metadata errors. It
preserves actionable continuation feedback instead of always demanding another
source edit. The server still requires changed source, executed incident tests,
an exact frozen package and fresh scientific reviews.

Native workers atomically retain completion receipts before Storage/SQL result
persistence. Recovery verifies the admitted request, original terminal stream,
transport fields, source identities and stopped container before appending a
service-only reconciliation. Older calls can use retained transport metadata
and an original complete stream. Missing metadata, incomplete streams, changed
bytes and active work remain fenced. Original unknown call and parent records
stay unchanged; commitments are never refunded and inference is not replayed.
Outbox intent is durable before publishing its completion payload.

The bounded TCP executor can recover its original captured response after an
ingestion interruption. It verifies the fixed artifact identity, complete raw
bytes, specification hash and transport receipt and retains original completion
time. Missing or legacy captures without sufficient metadata cannot relaunch.

Two new migrations are required before the matching worker/controller release:

- `202610300002_native_call_reconciliation.sql` adds private append-only native
  completion proofs and updates existing admission/recovery gates to recognize
  only matching reconciliations. Browser access remains denied.
- `202610300003_research_append_normalization.sql` compares immutable retries
  after PostgreSQL's normal typed conversion. The actual integration exposed
  identical UTC input timestamps being returned in America/Chicago and rejected
  as changed records. Equivalent instants now retry idempotently. Changed units
  and unknown fields remain rejected; original artifact bytes/hashes are intact.

## Qualification

- 422 backend tests passed. Infrastructure TypeScript compilation and all 100
  infrastructure tests passed with the backend checkout supplied.
- The actual OpenClaw CLI exercised native read/edit/write/exec tools against a
  pinned Linux/amd64 Docker image, emulated on an arm64 host. The final synthetic
  integration passed with seven synthetic responses and zero actual model calls.
- Live subscription qualification used 22 actual completed responses across
  retained development trials: 12, then 6, then 4. The first two trials exhausted
  their separately declared limits without a candidate. The corrected working
  packet then produced a changed source package, unchanged incident tests and
  valid metadata; the separate server container executed both tests successfully.
  The compiled candidate and validation bind the same frozen project hash.
- The last live trial's harness incorrectly demanded a new native exec despite
  fresh server-executed tests. Its failed report remains unchanged. A corrected
  retained-output review verified the original source baseline, unchanged tests,
  actual responses, server stdout/stderr, metadata and candidate with zero new
  provider calls. The first trial's application counter included a thirteenth
  transport entry rejected locally by the qualification guard; only twelve HTTP
  calls occurred in that trial. That original fixture receipt is retained.
- Real isolated PostgreSQL checks recover a lost native completion and its parent
  without rewriting either unknown row, duplicating inference or changing limits.
  They exercise exact identities, distinct call coverage, idempotency, active-work
  fences, RLS and browser denial. Cleanup is mocked in that SQL fixture; actual
  Docker tools and container validation are covered separately.
- The PDF-to-assessment fixture uses actual extraction, controller, native CLI,
  durable dispatch and SQL functions. After confirmation it runs one actual local
  TCP acquisition, intentionally interrupts result persistence, and starts a
  separate process to ingest the captured response with fresh executor calls
  forbidden. It finishes with one job/run, four measurements, two claim-specific
  findings (reproduced and discrepant) and 117 hash-verified artifacts. Model
  judgments, Google identity, wake delivery and Lambda transport are fixtures.
- The full Linux qualification retains all five loss conditions (0/1/2/5/10%),
  three invocations, 30-second CUBIC transfers, 100-Mbit/s shaping and 20-ms delay
  in each direction: 15 transfers and 75 recorded observations. Receiver
  byte/time/rate conservation and the unloaded RTT control passed without any
  directional goodput success criterion or discarded trial.
- A separate retrospective software campaign persists those 75 observations,
  three source invocations, full configuration, raw outputs and source/protocol
  identities in the real isolated research SQL schema. Duplicate writes retain
  one copy; changed units and unknown fields fail. A new process retrieves the
  records and hash-verifies their artifacts through a durable filesystem Storage
  transport fixture. Run timestamps describe import processing only: original
  acquisition UTC start/end were not recorded and remain explicitly unavailable.

The full-grid protocol's comparison prose retained an inherited smoke-test
reference to ten observations. Its explicit five-condition configuration and
three replications define 75 observations; all 75 originals are retained. That
wording defect is disclosed without rewriting the frozen protocol or treating
development invocations as independent-host replications. No confidence interval,
causal conclusion or result for the production paper is asserted.

## Reproduction

From `jumpserve-back-end`:

```sh
python3 -B -m unittest discover -s research_workflow/tests -p 'test_*.py' -q
python3 -B research_workflow/tests/check_native_repair_handoff_linux.py --amd64
```

The retained live result can be reviewed without new model calls:

```sh
python3 -B research_workflow/tests/check_native_repair_handoff_linux.py --verify-live-result 20261030T231115228195Z
```

From `jumpserve-infra`:

```sh
npm run test:research:builder
npm run test:research:completion
npm run test:research:netem-persistence
env JUMPSERVE_BACKEND_CHECKOUT=../jumpserve-back-end npm test -- --runInBand
npm run build
```

The netem persistence check imports the retained full-grid qualification; it does
not acquire new observations. The fixed Docker checks require the locally built
image and the database checks require isolated PostgreSQL on port 54477. Preserve
failed runs. Do not replay the live campaigns to inspect their results.

## Production boundary

Exact qualification on the installed production image/native Linux worker,
remote Supabase Storage, legitimate authenticated browser submission and the
original assessment's actual experiment completion remain unverified by this
local work. File-system Storage transport and synthetic model judgments are
clearly separate from live subscription qualification. Available token usage is
retained; monetary charges and subscription/host/storage allocations are unknown.
Review is by the implementing AI, not human, independent or held out.

An explicit deployment request is still required. A coordinated release must
apply both migrations before the matching runtime, qualify exact deployed source
and installed image, renew recovery approval, then resume only reconciled work
and observe actual ingestion. Preserve original criteria, commitments, deadline
and uncertain-call fences. Existing local 100-GB policy changes retain their
separate pricing/approval requirements; this work does not activate them.

The local status and hash-verified evidence archive are indexed by
`autonomy-recovery-execution-local-v1-status.json`.
