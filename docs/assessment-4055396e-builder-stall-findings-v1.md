# Why assessment 4055396e is not reaching experiments

The investigation found a repeatable context/read loop, a repair routing path
that requeues the no-progress stop, and a separate full-grid resource admission
conflict. Restarting the assessment has not been demonstrated to correct these
mechanisms. No runtime fix, restart, cancellation or deployment was performed.

This is a software investigation of assessment
`4055396e-35c0-4962-ba39-cf23e443ad8d`, not a reproduction of its scientific
claims. The uploaded document is explicitly labeled a fictional benchmark with
fabricated published values. Those values were not accepted as measurements.

## Evidence and conditions

The frozen protocol is
`assessment-4055396e-builder-stall-protocol-v1.json`. The main private capture ran
from 2026-10-29 23:08:39 to 23:13:18 UTC. An adaptive read-only follow-up retrieved
the largest native request from each task's latest completed sampled builder,
five repair records and 40 recent repair events. Separate reads are a changing
snapshot, not an atomic observation.

Coverage comprises all five confirmed claim tasks, 15 recent builder parent
dispatches, ten recent native request/response pairs, five checkpoints and five
additional requests. All **95 selected original artifacts** were retrieved and
hash-verified. The checkpoints retain **428 tool calls: 270 `exec` and 158 `read`**;
there were no `write` or `edit` calls. There were **no `project/` files** in any of
the five checkpoint inventories. An `exec` command can write files, so tool names
alone do not establish the absence of implementation; the actual inventories and
recent command records are the relevant additional evidence.

Of the 15 parents, 13 were complete with a recorded context-boundary stop and no
implementation files. Two were unknown at capture; they remain unknown in this
analysis. Last-call samples cannot reconcile an entire uncertain parent, and no
provider call was replayed. Completed parents used 2–10 provider calls, rather
than using their whole 180-second scheduling window to produce code.

The offline checks use backend revision
`4d42a1b05da29851d83e9696f91c16d43aa8b6b5`. All 55 local runtime files match the
release pin; the preceding release audit verified that revision in production.
This investigation did not repeat the full deployed-source audit. OpenClaw and
model versions remain those recorded in the original receipts.

## Findings

**1. The worker stops after reading, then begins another fresh session that
reads much of the same material.** The exact five retained requests reconstruct
to the following UTF-8 byte sizes after the production request normalization:

| Claim task prefix | Request bytes | Boundary bytes | Over boundary |
|---|---:|---:|---:|
| `2dfbd3d1` | 76,651 | 72,000 | 4,651 |
| `b9c00763` | 75,766 | 72,000 | 3,766 |
| `872f6faa` | 75,372 | 72,000 | 3,372 |
| `1fa0b903` | 73,006 | 72,000 | 1,006 |
| `258366b4` | 77,525 | 72,000 | 5,525 |

These requests satisfy the earlier model/identity and 256,000-byte ingress
checks but exceed the separate 72,000-byte admission threshold in
`experiment_builder._execute`. This deterministically explains their local
rejection **before another provider call**. It is not evidence of a quota,
credential or provider outage. The CLI's generic “couldn't reach the AI service”
message masks the local intentional stop in these matched cases.

Each request already includes a **16,456-byte OpenClaw developer message** and a
roughly **15,210–15,608-byte user bootstrap**, plus **5,165 bytes of tool schemas**.
Inspection then contributes continuation/index files, full repair/protocol
documents and outputs approaching 16,000 bytes apiece. Recent calls repeatedly
read those materials rather than writing the implementation. File-based context
preserves originals but does not, by itself, keep the model from reading too much
back into each fresh request. The data demonstrate this loop in the sampled
attempts; they do not prove that any proposed smaller packet will make a model
write correct code.

**2. The no-progress stop can be undone by autonomous repair routing.**
`autonomy.step` asks to block after targeted replanning returns the same
implementation fingerprint. `autonomous_repair.route` sees an active repair and
an implementation-category failure, transitions it to `diagnosing`, and returns
`queued`. The subsequent repair can schedule building again. Thus the message
“repair is required before further spending” does not enforce that stop.

An offline call to the actual router using each captured task/repair record
reproduced this conversion in **5/5 cases**, with all SQL/network functions
disabled or mocked. This is a controlled state-transition check, not a newly
recorded production event. **15 budget/deadline/cancellation controls** and
**five external-equipment controls** retained their stop states. These controls
demonstrate the routing defect without claiming that every historical charge or
retry was caused by it. A later public snapshot also showed a task marked queued
while displaying the unchanged-work stop reason.

**3. The full source-specified built-in sweep cannot fit its current byte
admission envelope.** The archived extraction identifies the original PDF as
SHA-256 `77becb203ef79c5e5d0b69ee9cfc5553e5680d2c44128aaa6b8f2c545d533617`.
Pages 2 and 5 specify 100 Mbit/s, 30-second transfers and the loss grid
`[0,1,2,5,10]`, with three trials per condition. For each host invocation,
`netem_iperf.network_budget` requires:

```text
100 × 1,000,000 / 8 × 30 × 5 × 10 + 10,000,000
= 18,760,000,000 bytes
```

The execution schema caps `max_network_bytes` at **10,000,000,000**. No value can
satisfy both checks for that full grid in one built-in invocation. The two-loss
headline subset requires 7,510,000,000 bytes and does not have this particular
conflict. The allowance counts forwarded bytes across multiple virtual
interfaces; it is neither measured traffic nor predicted billable Internet
egress. The code calculation and independent integer arithmetic agree, sharing
the same source/configuration assumptions. No physical experiment was run.

This supports the H2 planner's stated implementation/resource blocker. It does
not establish that every possible custom package or partitioned campaign is
infeasible, and shortening transfers or dropping conditions would change the
tested scientific scope.

**4. Some missing-input messages are stale rather than actual missing inputs.**
For example, the idle-RTT task asks for observation identities and null handling.
The full `netem-iperf-v1.output_contract` is already present in all five sampled
builder contexts, including loss key formatting, pre-transfer ICMP semantics and
missing/null handling. It remains important to distinguish stale model requests
from the genuine full-grid limit above. The causal window/queue claims also need
instrumentation and controlled mechanism comparisons; throughput alone cannot
resolve those claims.

## Recommended correction and verification

1. Give each build a bounded work packet: the specific implementation task,
   applicable input/output contract, required source passages, real file state
   and actionable feedback. Keep complete originals accessible by verified
   references. Budget the actual native request, including OpenClaw's developer
   message and tool schemas. Preserve original history rather than repeatedly
   loading it in full or representing shortened views as complete evidence.
2. Preserve useful implementation feedback separately from scheduling messages.
   A context checkpoint should not become the whole next task. Require the next
   repair to change the work plan or relevant configuration and validate that
   change; re-entering an identical read cycle is not recovery. This is a
   progress criterion, not a new AI-turn cap.
3. Correct the conflict between the no-progress stop and repair routing. The
   unattended resolver should diagnose and repair the specific integration
   failure, with a versioned change and regression evidence, rather than
   continually enqueue the same build instructions. Preserve limits and all
   failed/unknown original identities.
4. Resolve the full-grid byte admission design under the existing spending
   authorization. Verify the units and actual counters, then qualify an honest
   envelope or a scientifically equivalent partitioned campaign. Do not silently
   lower the accounting factor or alter the paper's transfer duration/loss grid.
5. Qualify the resulting candidate against this actual full-context paper flow:
   implementation files, real bounded development execution, frozen package,
   fresh scientific reviews, queue job creation and actual measurement
   ingestion. Reused cases are development regressions; add genuinely held-out
   papers for generalization checks. The earlier doubling/file-reading fixture
   established tool capability under its conditions, not full-paper autonomy.

Restarting alone is not an established remedy. A later clean-context comparison
could investigate retained-context effects while preserving the earlier
assessment and accounting, but no such live comparison was performed here.

## Reproduction and limits

Run from `jumpserve-infra`:

```sh
python3 -B bin/inspect-builder-stall-4055396e.py
python3 -B bin/inspect-builder-stall-4055396e.py --requests
python3 -B bin/analyze-builder-stall-4055396e.py
```

The first two commands perform fixed-target read-only retrieval. They do not
restart models or experiments. The third is offline and blocks database calls
in the state-transition controls. A corrected analyzer followed an initial
development harness failure caused by referring to `route` by the wrong name;
that failure is not a production defect.

The investigator made **zero new model calls and ran zero new experiments**.
Hosting/storage charges and subscription allocation are unavailable, not zero.
The assessment continued independently during observation. The public snapshot
at approximately 23:20 UTC showed **$458.20 committed of $1,000**, five untested
claims and zero experiment jobs. Commitments are reservations, not measured
charges. This is not a live cost estimate.

Original artifacts and all histories are retained, but hash verification is not
full review: selected recent commands, native responses and five exact boundary
requests were examined; not every historical output byte was substantively
reviewed. Extracted text from five pages was examined for scope/settings; the
original PDF figures, references and supplements were not newly reviewed. No
scientific claim was classified as reproduced or discrepant by this work.

The investigator/reviewer is the implementing **AI**, not a human or independent
reviewer. No confidence intervals are appropriate for these dependent selected
software traces. The private artifact receipt is recorded separately in
`assessment-4055396e-builder-stall-retention-v1.json` after storage verification.
