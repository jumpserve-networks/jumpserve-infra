# Assessment evidence-reading progress

Qualification: 637 isolated AWS Linux software checks passed with zero model
calls. The exact source binding and inherited execution scope are recorded in
`assessment-reading-progress-qualification-v1.json`. Use the private Platform
Updates release receipts to establish production activation; software
qualification does not establish live model recovery or scientific completion.

The observed planning failure repeatedly requested runtime-contract cursors
`0`, `1500`, `3000`, `4500`, then restarted at zero. The controller supplied only
the latest fragment and three recent decisions, so a planner could lose the start
of the contract as it reached the end. A fresh heartbeat did not establish useful
assessment progress.

`autonomy_read_progress.py` retains a bounded window in the existing claim task's
Supabase JSON context. Each receipt binds the exact request, content hashes,
next cursor, result hash and originating numbered turn. Up to 32 receipts and
16,000 canonical bytes of original page envelopes are retained for later prompts.
Omissions are explicit; the complete audit stays in the original numbered
requests/responses. The window is isolated by phase and exact candidate hash.
Fresh comprehension and critic reviews do not receive another role's window.
Delivery counts never constitute substantive review or scientific coverage.

Three repeated unchanged page reads without a new page create a durable runtime
repair incident through the existing controller. A four-page cycle counts as
repetition even though consecutive cursors differ. New turn IDs and changing
source-delivery counters do not count as new evidence. Changed page/document
content does. This is a bounded detector for revisits within the retained window;
it does not claim to identify every possible planning failure or cycles larger
than the window.

Recovery first uses the existing reconciliation gates for original calls and
jobs. A running or uncertain call prevents replacement work. The repair retains
the page window, adds explicit end-of-document/progress guidance and validates
the actual corrected model request, including the OpenClaw wire-size limit,
before resuming the original phase. It does not change claims, frozen criteria,
measurements, counters, commitments, deadlines or job identities. Original repair
incidents and diagnosis artifacts remain immutable.

An unchanged recurrence after that correction stops further model calls for the
task and leaves an explicit platform repair blocker. The same correction is not
repeated merely because another turn or repair could be allocated. New evidence
or changed adapter source can justify a different recovery. The existing
[assessment blocker outbox](assessment-blocker-repairs-v1.md) captures repair
diagnoses and blocked tasks transactionally, independent of daily maintenance.
Worker pickup and successful release still require available capacity and the
installed qualified adapters.

Verification:

```sh
python3 -B -m unittest discover -s research_workflow/tests -p test_autonomy_read_progress.py -v
python3 -B -m unittest discover -s research_workflow/tests -v
```

Run these in `jumpserve-back-end`. Fixtures exercise the actual bounded reader,
controller routing, request serialization and repair adapter without providers,
cloud launches or scientific measurements. They verify operational software
behavior, not model efficacy or unattended paper completion. Deployment must
include the new module in the exact runtime manifest and qualify the changed
source before activating it. No database migration or frontend change is needed.
