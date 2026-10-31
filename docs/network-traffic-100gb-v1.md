# 100-GB runner allowance and remaining assessment blockers

Historical local implementation record. See [the integrated release](integrated-research-release-v1.md) for current qualification and production verification.
Production remains on its existing pinned runtime and policies. The current
runtime manifest and the historical policy bytes have not been changed.

The user requested a 100-GB network-traffic allowance. Here GB means decimal
bytes: 100,000,000,000 per experimental invocation, not GiB, storage, per-paper
usage or a monetary budget. Two executable paths receive new v3 policies:

- Fixed `netem-iperf-v1`: ceiling increases from 20 GB to 100 GB.
- AI-built `built-package-v1`: ceiling increases from 10 GB to 100 GB.

The previous statement that the fixed runner was limited to 10 GB came from an
older retained blocker. Its current v2 policy already permits 20 GB, sufficient
for the unchanged 18,760,000,000-byte admission formula for the five-condition
100-Mbit/s, 30-second sweep. The AI-built runner retained the 10-GB ceiling. Both
paths are updated so that moving between them does not reintroduce that ceiling.
Generic `custom-package-v1` and other runners retain their existing policies.

Compiler validation, planner contracts, immutable policy selection and cost
quoting agree on the new ceilings. The compiler preserves a smaller requested
allowance; it does not raise every invocation to 100 GB. Original protocols,
scientific criteria, durations, conditions, replication counts and observations
are not edited. One host, 30-minute wall limit, 3-MB output allowance, cancellation
and independent deadline cleanup remain required.

The guard samples non-loopback receive/transmit counters in the runtime network
namespace. Child namespace counters are retained in raw diagnostics and are not
included in that sampled guard. Forwarded traffic can be counted more than once;
missing/reset counters stay missing. This is not Internet-billing calibration,
adversarial metering or a hard invoice cap. The fixed netem admission formula
allows for repeated interface counting; changing its ceiling does not change
that formula or predict goodput.

Both new policies remain unapproved for execution until a new release passes
qualification. The built-package policy proposes a $20 conservative reservation
instead of inheriting the earlier $10 approval. This is provisional pending fresh
retained AWS pricing evidence and review, not a measured charge or an estimate
of every run's actual cost. The fixed runner retains its proposed $1 reservation
because its larger counter envelope does not add public experiment targets,
hosts or execution time. Existing paper commitments and the default $100 budget
are not amended by these local changes.

The versioned development protocol is
`research_workflow/policies/network-traffic-100gb-validation-v1.json` in the
backend. Local checks passed 403 backend tests, 100 infrastructure tests and
TypeScript compilation. They cover exact-ceiling admission, ceiling-plus-one
and invalid-value denial, policy approval, stale hash and expiry denial,
unchanged host/time/output bounds, and source-grid preservation. A real child
process with controlled counters was allowed at exactly 100 GB and terminated
above it with the sampled delta retained. No 100-GB traffic campaign, real
model answer, new Linux qualification or scientific result is claimed. An
initial infrastructure run omitted five checkout-dependent checks; the full
rerun supplied `JUMPSERVE_BACKEND_CHECKOUT` and passed all 100 without skips.

For assessment `4055396e-35c0-4962-ba39-cf23e443ad8d`, the public queue was read
without database writes or new model/experiment calls. The implementation-stalled
claim's retained response asks for native file tools while describing a
planning-only interface. This is evidence of an interface/handoff problem to
trace, not proof that every stalled turn lacked tools. The next work should be:

1. Reconcile the stalled claim's exact task stage, original logical request,
   response, checkpoint and tool history. Ensure the repair stage dispatches to
   the native builder with the existing project, file writes and command tools.
   Require an actual change to `experiment.py`, incident-bound development
   regression tests and a frozen candidate before fresh scientific reviews.
   Retain the no-progress guard; do not merely reset it or repeat the prompt.
2. Reconcile the expired worker operation using its original dispatch/request
   hashes, receipt, retained response and checkpoint. A completed original
   response should be ingested; a demonstrably pre-provider failure may resume
   through the audited recovery path. A genuinely uncertain invocation stays
   fenced. Never replay it because a lease expired.
3. For the queue/recovery causal claim, implement and validate recovery/window
   and queue instrumentation plus controlled interventions. A goodput sweep can
   supply shared measurements but does not by itself demonstrate that mechanism.
   Keep this claim's causal criteria separate from numerical loss-sweep results.

Production release requires an explicit request, verified AWS account
`395567831870` and JumpServe Supabase project `regphejnlvfpyokpniny`, fresh pricing
review, exact-source Linux operational qualification and renewed recovery
approval. A new committed manifest must explicitly include the v3 policy files
before CDK selects them; historical manifests retain their old policies. Hold
admissions during the coordinated host/API/executor rollout, verify hashes and
the effective limits, then resume only reconciled tasks with an append-only
audit. Replace obsolete working feedback with current contracts while retaining
its original source. Do not restart the assessment or change its deadline to
apply this resource correction. No production mutation occurred in this task.

Review was performed by the implementing Codex AI, without independent or human
review. The development cases are exposed regressions, not held-out validation.
