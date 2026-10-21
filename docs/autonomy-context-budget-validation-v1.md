# Context size pauses: local correction

This change is local and uncommitted. No production migration, deployment, prompt
publication or task recovery was performed by this editing request.

The quoted error is raised before the model-turn admission RPC or provider call.
It is a serialized AI request limit, independent of PDF upload size. Existing
scientific findings and original artifacts are retained when a task pauses.

Read-only diagnosis verified AWS account 395567831870 and Supabase project
regphejnlvfpyokpniny, then examined one matching historical IPv6 planning pause.
The original record comes from an October 18 release-verification study. Its
current rebuilt context is 49,194 bytes; with the active published prompt, tools
and JSON framing, the request is 68,060 bytes and fits the existing 96,000-byte
limit. It has zero model attempts. This identifies one recoverable historical
pause; the user's exact assessment has not been identified without its link.
Do not infer that every reported context failure now fits.

The existing recovery implementation tries each task once per version. A pause
retained after that attempt can continue displaying its historical error even
when newer request construction fits. The correction adds a separate, versioned
service-only recovery gate. The controller first rebuilds and serializes the
current request using the verified active prompt, without invoking a model. Only
a fitting request may reach the recovery RPC. The RPC checks ownership, original
deadline, spending and attempt limits, task status and phase, and unconfirmed
provider or experiment identities. It records the request hash and byte count,
preserves original prompts, context, counters and commitments, and permits one
recovery under this implementation. It does not declare a scientific finding.

For genuinely oversized planning requests, the controller replaces only inline
check-selection details with an index containing every original check ID,
protocol reference and hash-bound read reference. Full protocols, configurations,
inputs, numerical data, prior answers and feedback are retained. A referenced
selection document that exceeds a record page is readable through explicit
canonical JSON fragments. Selected experiments still receive their original
fresh reviews. Fitting requests remain byte for byte unchanged. The 96,000-byte
guard remains enforced for irreducible contexts and large system prompts.

The controlled development regression makes a selection view larger without
overwriting the archived campaign. The released implementation rejects it with
the reported error. Its original context is 192,667 bytes; the corrected complete
provider request is 29,332 bytes, with all six check identities retained. This is
a software fixture, not a reproduced paper result or a held-out model evaluation.

Validation passed:

- 174 backend tests, including byte-budget accounting, nonmutation, complete
  fragmented check readback, irreducible limits and zero-call recovery preflight.
- 93 infrastructure tests and the infrastructure TypeScript build.
- Eleven actual local Postgres/controller/worker groups, including recovery after
  an earlier version's attempt, preservation of prompt hashes, budgets, deadlines
  and counters, malformed/oversized preflight rejection, one-time recovery, wrong
  owner denial and browser RPC denial. Other groups cover actual archived
  arithmetic, the actual PDF parser, parallel budget/slot enforcement and bounded
  loopback TCP. Provider, authentication, Storage and cloud SDK responses are
  explicit fixtures in that campaign.

Failed diagnostics and campaigns remain in their original directories: sandbox
network denial, local certificate-store mismatch, a stale development source
manifest rejected by the fixture guard, and an RPC missing from the explicit
fixture allowlist. The publication guard and historical evaluated profiles were
not weakened. The corrected local campaign uses separately declared runtime v30
working-tree hashes; published v29 remains in git and its production archive.

The actual diagnostic source/context bytes stay in ignored private local evidence.
The committed-report candidate contains hashes and sizes, not private source text
or credentials. New provider calls and production mutations are zero. Local
compute, storage and diagnostic API charges are unallocated, not measured zero.
Primary AI implementation/review is neither human nor independent review.

Reproduction commands are the standard backend suite, infrastructure build and
full suite, plus `npm run test:research:autonomy` using the existing isolated
Postgres cluster on localhost:54477. The read-only diagnostic command is
`python3 -B bin/diagnose-autonomy-context.py`; it verifies fixed targets and never
resumes a task. Exact original evidence paths and hashes are recorded in
`autonomy-context-budget-validation-v1.json`.

A later explicitly authorized release must commit and pin the exact backend,
apply `database/202610200002_context_budget_recovery.sql`, and deploy the matching
runtime and `autonomy-context-budget-v1` recovery flag together. Verify real
provider behavior for the new indexed context and the affected study's actual
recovery before calling it verified in production. The published prompt remains
v8; the local software fixtures do not constitute fresh actual-model evaluation.
