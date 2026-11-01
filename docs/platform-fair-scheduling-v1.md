# Fair host admission for platform repairs

Release scope: database only. Production activation and observed scheduling
evidence are recorded separately in Platform Updates.

The live status audit on 2026-11-01 found a ready, unpaused supervisor, 24 queued
tasks and ongoing research dispatches. Recent supervisor claims only closed work
whose original deadlines had already passed. The old host gate gives research
priority without reserving capacity for repairs, so continuous assessment work
can keep a repair queued until it expires.

## Admission behavior

Migration `202611010006_platform_repair_fair_scheduling.sql` adds one private
scheduler row and wraps the existing parent-lease and supervisor RPCs. Worker
code, model transport, category budgets, authority and fixed release checks do
not change.

- On the existing 15-second supervisor claim loop, an eligible task receives a
  reservation lasting at most ten minutes. Repeated polls keep its original
  expiry. Eligibility requires the original authorization, ready time and enough
  remaining task/assessment time. Stopped parents and cancelled ordinary tasks
  cannot reserve capacity. Reconciliation retains its existing exception for
  inspecting original outcomes after cancellation or expiry.
- During the reservation, new research **parent leases** wait. Research parents
  already admitted can enqueue and complete their original model dispatches.
  Native dispatch claims retain their existing gate. The supervisor also waits
  for live parent leases, closing the gap before an original parent enqueues.
  Existing calls, renewals, responses and experiment operations are not stopped.
- The original supervisor RPC must acquire the selected task's fenced lease.
  Its existing native mutual exclusion, reconciliation, cleanup and scoped-task
  checks remain authoritative. A pre-existing lease is adopted on upgrade;
  an expired lease must reconcile through that same task and controller.
- Each durable supervisor checkpoint releases the reservation and gives research
  sixty seconds of admission before another repair reservation. Among tasks at
  the same priority, the least recently claimed task goes first. This prevents
  an incomplete repair from taking every available turn. Existing cleanup fences
  and separately qualified runtime maintenance holds still govern admission;
  a runtime hold can only be created for the selected task.
- Pending reservations stop holding research when they expire, the worker
  heartbeat becomes older than sixty seconds, the task becomes ineligible or an
  owner pauses admission. A subsequent supervisor poll releases the reservation
  and starts the sixty-second cooldown. Expiry never extends a task deadline.
- Expired queued or development work with no unresolved model/operation/cleanup
  is recorded as `deadline` without acquiring a coding turn. Its checkpoint,
  spending, attempts, original deadline and receipts stay intact. Uncertain work
  is retained for reconciliation.

The ten-minute bound applies to waiting for admission. It is not permission to
interrupt a leased coding call or an external release operation. Once admitted,
the existing bounded coding slice, fixed-check timeouts, checkpoints, original
deadline and uncertain-call safeguards continue to govern that turn. Long or
unresolved original work can still prevent repair admission; no scheduler can
safely declare an unknown call complete.

Reservation and checkpoint events appear in the existing private Platform Updates
history as `host-turn-reserved` and `host-turn-released`. The scheduler table has
RLS, service SELECT only and no browser access. Internal helpers and previous RPC
implementations cannot be invoked directly by workers or browsers.

## Verification and release

Run against the existing isolated loopback PostgreSQL test server:

```sh
python3 -B test/check_platform_fair_scheduling_database.py
```

This executes the existing funding, repair, reconciliation and polling SQL checks
unchanged, then installs the migration and exercises actual concurrent database
claims. Cases cover draining an original queued dispatch, reserving capacity
under continuous demand, research admission between repair turns, task rotation,
reservation expiry, stale workers, owner controls, exact scoped claims, stale
lease recovery, cleanup fences and unchanged retained unknown calls. Test clocks,
Google identity, Storage and provider transport are synthetic; no Docker or cloud
operation is performed.

After an explicit deployment request, apply this migration through the existing
project-locked migration path. Both RPCs change in the same transaction under
the established research-then-platform lock order. No worker reinstall, frontend
build, new AWS host or research runtime revision is needed. Verify service-only
permissions, fresh heartbeats, a recorded reservation followed by a genuine repair
lease/model action, and renewed research activity after a supervisor checkpoint.
Healthy worker heartbeats alone do not demonstrate this behavior. Keep original
expired tasks and unresolved calls; do not grant them replacement deadlines or
report assessment completion merely because a repair received a turn.
