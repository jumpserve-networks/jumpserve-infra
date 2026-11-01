# Semantic repair evidence and unclaimed queue recovery

Qualified on isolated AWS with 550 checks and no copied model grant. See the
[exact qualification](queued-recovery-qualification-v1.json); production activation
is recorded separately in private Platform Updates. This follows
[the incident handoff](platform-repair-handoff-v1.md).

The production readback found that `task-transition.details.usage` changed on
each controller wait. Its nested `controller_wall_seconds` made the incident
fingerprint change, so a correctly blocked platform repair was repeatedly woken.
The original builder dispatch also remained queued after its controller turn
ended. Existing retained-result recovery handled terminal dispatches and skipped
this unclaimed queue entry, while the sandbox correctly lacked credentials to
reconcile it itself.

`202611010003_platform_repair_semantic_evidence.sql` removes controller usage,
clock, scheduling and attempt-counter fields from the wake decision. It retains
distinct diagnostic content, original request/response/source hashes and actual
ledger outcomes. Every full original event remains in the packet and private
database history. Records containing only bookkeeping cannot supply new evidence.
Changing this fingerprint protocol appends a semantic baseline to already blocked
guards; it does not restart them, discard their old report or reset their slice
counter. The worker understands that appended baseline across restarts.

`202611010002_queued_dispatch_recovery.sql` adds service-only atomic recovery for
pristine queued builder admissions. The function locks the original dispatch and
terminal parent under the existing admission locks. It requires exact request,
model and study/task identities, no worker lease, no response/provenance or worker
artifacts, and no native calls for that dispatch. A concurrent worker claim wins
by changing the locked row to running; recovery then refuses to close it. A
claimed dispatch cannot return to the pristine queue state.

Eligible closure stores the exact original dispatch snapshot and its hash in a
private immutable reconciliation record, then terminalizes the still-queued
admission as failed. The original terminal controller turn remains unchanged.
This is positive queue-admission proof before a worker claim, not a conclusion
drawn from a missing local file or failed turn alone. It makes no container-cleanup
claim and performs no provider call, result rewrite, refund, budget change,
deadline extension or scientific validation. Running/unknown dispatches and native
unknowns retain their existing reconciliation requirements.

The existing AWS worker's bounded retained-result scan processes these candidates
without credentials entering the coding sandbox. Accounted admissions are excluded
before the candidate limit so they cannot starve other recoveries. Research repair
diagnosis accepts only the hash-verified immutable server record. The new proof
and changed dispatch outcome enter the platform incident packet, allowing one
genuine evidence-driven wake of the retained repair. All original scientific
criteria, checkpoints and subsequent validation remain effective.

Verification:

- `python3 -B -m unittest discover -s research_workflow/tests -v`
- `python3 -B -m unittest discover -s platform_supervisor/tests -v`
- `python3 -B test/check_repair_recovery_database.py` in infrastructure.

The database entry point retains the previous funding, maintenance, native-call
and scoped handoff checks, then exercises the observed nested-usage failure,
blocked-state upgrades, immutable queue snapshots, browser denial, wrong request
hashes, unknown/native fences, scan fairness and a real concurrent SQL claim.
It uses isolated retained loopback PostgreSQL, synthetic identities and no
provider, Docker, AWS or production mutations. Protected infrastructure CI runs
this combined entry point.

For a later authorized production release, qualify the exact research-runtime
changes through the existing dedicated checks and versioned pin procedure; do not
install loose runtime edits or amend its qualification policy to manufacture a
pass. Drain platform admissions and original work through the existing maintenance
procedure. Apply 002 followed by 003 to project `regphejnlvfpyokpniny`, then install
the qualified research runtime and reviewed platform worker. The bootstrap list
also registers both incremental migrations for future installations. Do not rerun
operator enrollment or reset existing task checkpoints. No frontend release or
new AWS role is needed.

Activation verification must show an actual stored unclaimed-admission proof,
unchanged terminal parent/counters/deadline and a wake caused by that proof rather
than telemetry. A queued admission closure is not a completed research assessment
or evidence of a successful source correction; verify resulting repairs separately.

The subsequent private-contract delivery and proof-query correction are described
in `platform-repair-recovery-contract-v1.md`. Version 80 closed the original queue
admission but its diagnosis reader still used a nonexistent generic `id` sort key.
