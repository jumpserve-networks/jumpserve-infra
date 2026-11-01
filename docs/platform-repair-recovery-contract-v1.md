# Recovery contract delivery and the actual proof query

A read-only diagnosis using the installed version-80 runtime identified the
current failure: `GET /rest/v1/research_queued_dispatch_reconciliations` returned
HTTP 400. The real client applied `created_at.asc,id.asc` to a table keyed by
`dispatch_id`, with no `id` column. Earlier unit checks mocked the row reader,
and earlier SQL checks read the table directly, so neither exercised this query.
The production diagnostic admitted no provider calls and changed no research row.

The correction gives this private relation the same explicit dispatch-key order
as model reconciliations. Browser reads remain denied. Diagnosis continues to
verify the immutable original snapshot, exact request/study/task bindings and
atomic pre-transport proof. This change does not replay a model call, treat a
missing result as zero transport, claim container cleanup, reset a deadline or
alter scientific validation.

The supervisor's original workspace also predates the deployed reconciliation
adapter. Migration `202611010004_platform_repair_recovery_contract.sql` supplies
the installed private schema, query order, actual constraints/triggers, permission
checks and hash-bound reconciliation function definition through the existing
lease-checked incident RPC. Direct browser and service invocation of the helper
remain denied. These are diagnostic references, not SQL execution authority.
The contract enters the semantic evidence revision, so delivering genuinely new
contract information can wake the original blocked repair without a timer reset.

Current diagnosis references are selected from the linked repair's persisted
evidence, including waiting diagnoses not copied into task.context. Their original
bytes are delivered only after the existing study/path/size/hash checks. A missing
diagnosis remains missing; queue closure is not presented as successful diagnosis
or assessment resumption.

Before coding, a contract-aware, untested repair refreshes stale repository
revisions from exact GitHub main hashes. It retains an immutable working checkpoint
and refresh plan before replacing source. Independent edits, executable modes,
zero-byte files and deletions survive. Overlapping and protected proposals are
retained in previous-candidates for review while current main stays intact. Old
ready proposals are archived. A pending plan completes the same hash-checked
directory swaps after restart, including reconstruction on a replacement host;
unexpected source changes stop further work. Qualified candidates retain their
existing publication/rebase/reconciliation path. No limits or guard counters are
reset by a source refresh.

Verification entry points:

```sh
# Backend
python3 -B -m unittest discover -s platform_supervisor/tests -v
python3 -B -m unittest discover -s research_workflow/tests -v
# Infrastructure; dedicated local PostgreSQL on 54477, or the CI fixture URL
python3 -B test/check_repair_contract_database.py
```

The SQL entry point retains all earlier recovery checks, executes the real Python
proof reader and read-only diagnosis against the actual migrated table, and
verifies that the original `id` query fails. It also checks private installed
contract delivery, original-row preservation and diagnosis references. It does
not substitute a successful response for an invalid SQL ORDER BY.

These edits are local until an explicit production release is requested. That
release must qualify the changed research runtime and update its versioned source
pin/approval through the existing exact-source procedure. Do not amend an old
qualification record or install a loose runtime edit. Apply 004 after 002 and 003,
install both qualified workers, and verify a newly persisted controller diagnosis
and resulting claim progress. Preserve any expired original task deadline and all
uncertain-call fences. No frontend change or new AWS permission is needed.

Local verification on 2026-11-01 passed 454 research tests, 47 supervisor tests,
53 actual PostgreSQL checks and 13 release checks (567 total). These software
checks do not establish a production release or completed research assessment.
The research-runtime approval and pin remain unchanged pending exact-source
release qualification; no existing gate or scientific test was relaxed.
