# Native implementation repair handoff

Status: implemented and verified locally. No merge, push, deployment or
production assessment mutation occurred. Existing 100-GB changes remain local
alongside this work; the production runtime manifest and published prompts are
unchanged.

The public history of assessment `4055396e-35c0-4962-ba39-cf23e443ad8d`, task
`b9c00763-023d-5971-9367-e02d30949d7c`, records an implementation repair entering
planning turn 263. That request had the data-only planning tool surface. Its
response asked for access to the native file/command interface. Later controller
turns 264 and 266 used builder requests, and native calls through 270 were
retained. Thus an unnecessary planning-only hop is demonstrated; absence of
native tools is not established as the cause of every later stalled turn.
Only the first public fragments of native call 270's request and response were
examined. Their original hashes identify the unchanged originals; public
fragments are redacted derived views, not complete original-byte retrievals.

An incident-bound `native-repair-handoff-v1` record now routes an unfinished
implementation repair to `building` before model admission. The controller
persists this transition and keeps the original checkpoint, attempt numbering,
claim criteria, commitments and deadline. Missing native runtime availability
stops without a planning-model fallback. The model boundary rejects a stale
planning request carrying implementation repair instructions.

No-progress feedback for a repair now remains in the native builder. A newly
listed sibling package cannot divert an unfinished repair to planning; normal
non-repair package reuse keeps its existing behavior. The original repeated
recovery-key stop remains, so unchanged code is not an unlimited retry strategy.
Actual native request schemas must include `read`, `write`, `edit`, `exec` and
`process`, with the existing allowlist retained. Missing tools stop before
provider transport.

The handoff binds the original incident checkpoint as a pre-repair source
baseline. If no checkpoint was recorded, the worker freezes its actual
workspace before tools run; it does not assume that missing metadata means an
empty workspace. That immutable reference persists across continuations and
failures. The validator verifies its bytes and rejects an unchanged
`project/experiment.py`. A changed source file is evidence of a byte change,
not evidence that the repair is correct.

Candidate admission still requires both incident-bound development tests to
execute actual functions, the exact frozen source ZIP and the matching server
validation receipt. The existing read-only, network-free validation container
retains stdout, stderr, exit status and failed checks. Active repair records
resolve through their existing versioned transitions. A historical budget-stop
record is preserved while a separately recorded validated candidate may
continue. Editing instructions are cleared only after matching incident,
baseline and frozen project checks; fresh comprehension/critic reviews remain
required. Cancellation, budget and deadline controls never require candidate
validation to stop.

The frozen development protocol is
`research_workflow/policies/native-repair-handoff-validation-v1.json` in the
backend. All 414 backend tests passed, including eleven new routing, source
identity, no-progress, tool-surface, cancellation and review-boundary cases.
The unit suite uses persistence/provider fixtures and real local subprocesses;
it is not an authenticated database or production evaluation.

The fixed integration command is:

```sh
cd /Users/Shared/allstar/jumpserve-back-end
python3 -B -m unittest discover -s research_workflow/tests -p 'test_*.py' -v
python3 -B research_workflow/tests/check_native_repair_handoff_linux.py
```

Its final run was
`.test-artifacts/native-repair-handoff/20261030T225136626348Z`. It exercised the
real model-call router, local OpenClaw CLI and pinned Linux/arm64 Docker image.
Seven synthetic inference responses caused actual read, failing command, source
edit, metadata write, passing command and candidate-write operations. The server
then separately executed the two fixture tests in its restricted validator
and froze a candidate whose project hash matched the validated source. No
paper experiment or scientific result was produced. Model transport, controller
persistence and package registration were local fixtures; no external model
call, AWS instance or production write occurred.

Failed runs remain retained. The first Docker attempt was blocked by sandbox
access before any synthetic inference. Two subsequent runs completed native
candidate generation but failed harness postprocessing: the simulated dispatcher
first omitted its runtime receipt, then the harness assumed provider call IDs
instead of matching actual normalized native call/output identities. Corrections
were followed by passing integration runs. Across the four executed native
trials there were 28 synthetic responses and zero actual provider calls; they
are exposed development cases, not independent replications or held-out checks.
The final trial additionally followed the cancellation guard regression. Earlier
unit red/failed-fixture logs are preserved separately.

Validation artifacts, original public projections, source snapshots and hashes
are indexed by `native-repair-handoff-local-v1-status.json`. Original invocation
logs and native outputs remain under the backend's `.test-artifacts`. Usage in
synthetic responses is fixture data, not measured model consumption. Monetary
charges and unallocated local compute/storage costs remain unknown.

The production Linux/amd64 image, real subscription behavior, database writes,
new browser flows and the affected claim's experiment completion were not newly
verified. A release still needs the explicit deployment request, exact-source
qualification and renewal of the existing repair approval, followed by an
audited resume of eligible reconciled tasks. Do not replay an uncertain call,
reset the assessment or remove its no-progress stop to activate this fix.
Review was performed by the implementing Codex AI, without human or independent
review.
