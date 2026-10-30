# Builder stall fixes — local implementation

The context loop, ineffective no-progress stop and five-loss admission conflict
identified in `assessment-4055396e-builder-stall-findings-v1.md` have local fixes.
No merge, push, deployment, restart, cancellation or assessment-label change was
performed. The only remote write is a private validation artifact linked to the
existing assessment. Scientific results remain separate from these checks.

## Changes

The builder now writes a bounded `work-packet.json` with the executable interface,
claim, actionable feedback, actual implementation inventory and original source
references. When applicable, it includes the already available netem observation
mapping, missing/null rules and units. A reader can retrieve one exact extracted
paper page without loading the full context. The complete original context and
history remain unchanged and hash-bound. Modified working paper text is rejected
against its retained original hash.

Context delivery is versioned as `builder-context-files-v2`. Index entries no
longer repeat lengthy reader commands and field hashes; the hashes and original
page-delivery proofs are retained separately in `delivery-proofs.json`. Recent
continuation metadata refers to previous tool outputs instead of recursively
quoting earlier indexes. These views are explicitly incomplete and do not assert
source comprehension or scientific review.

All supplied trusted logical system instructions remain whole. The supplementary
bootstrap avoids duplicating claim/directive documents already in the packet.
Every native request still passes the original **72,000-byte** admission check,
including the actual OpenClaw developer prompt, tool schemas, reasoning and
outputs. No sent history is silently shortened. `native-context-budget.json`
records that actual footprint. A scheduling/context notice is stored separately
from implementation feedback; legacy scheduling notices are not presented as the
coding task.

The controller now distinguishes recovery strategies by executable source hash
and implementation fingerprint. A changed adapter can receive a new targeted
replanning opportunity. A repeated unchanged strategy records `builder_stall`
and remains blocked through the actual repair router, instead of being converted
back to queued diagnosis. Budget, deadline, cancellation, source-integrity and
unknown-provider fences remain. This introduces no AI-turn cap or limit reset.
A blocked integration still needs a substantive validated correction; this
change does not implement arbitrary production self-patching.

The fixed netem runner has a new **20,000,000,000-byte interface-counter** maximum.
The source's five loss levels, 100 Mbit/s and 30-second transfers therefore admit
their unchanged **18,760,000,000-byte** allowance. The accounting factor remains
10, with the same extra 10 MB; this is not measured Internet egress or a billing
estimate. Tests preserve all five conditions and three replications. Other
built/custom runners retain their 10 GB bounds.

`netem-iperf-costs-v2.json` preserves the old host, wall, disk, reservation and
expiry, and adds the explicit counter/output bounds. It is **not approved for
execution**. Cost admission requires operational approval and a matching immutable
executor/policy hash. Historical v1 remains unchanged. CDK supports the old pinned
manifest and will select v2 only when a new manifest explicitly includes it.
The old exact-source repair approval is also cleared. No future release may reuse
the earlier approval evidence for these changed sources.

## Verification

- **388 backend tests passed**, including the regression that previously stopped
  only before entering the real repair router. It now tests the complete advance
  path, source-page identity, actionable feedback, full-grid compilation, exact
  counter bounds and policy-hash/qualification denial.
- **94 infrastructure tests passed**, with five existing conditional skips.
  TypeScript compilation passed. Infrastructure asset construction still uses
  the existing committed runtime pin; v2 policy validation has a separate
  deterministic test. This is not a new staged/deployed runtime verification.
- The real local OpenClaw CLI and Docker completed their three existing native
  continuation/permission controls with synthetic responses.
- An additional native check used a **67,412-byte actual retained paper context**.
  With a fixed synthetic tool plan it read the packet and source page, wrote a
  conditions parser and executed zero/null checks. Its six synthetic provider
  requests stayed at or below **49,133 bytes**. No real model chose that plan, no
  scientific measurements were generated and no package was published.
- The native image was
  `sha256:ef9eec8c7c44fa2da5312721295aeea6ee92837a8e7f909c5f70785ecb9207be`,
  **Linux ARM64**. This is not qualification on the production Linux AMD64 image.

Five counterfactual fresh packet-read requests, retaining the real native
developer/tool overhead, occupy **43,123–43,864 bytes** under the unchanged 72 KB
bound. Four reconstructed historical sequences also fit after replacing only
generated metadata. The fifth still occupies **72,948 bytes after ten old
reads** and must be stopped. This was not relabeled as accepted. Three failed
initial replays and the later versioned validation amendment remain retained.
The evidence supports bounded context delivery, not a guarantee that a real
model will stop rereading or produce a scientifically valid experiment.

All cases are exposed development regressions, reviewed by the implementing AI;
none constitute independent, human or held-out scientific validation. The
investigator used no live model calls or cloud instances. Storage/compute charges
and subscription allocation are unavailable, rather than recorded as zero.

The sealed archive excludes transient state databases, caches and private bridge
configuration. Original captured requests, responses, checkpoints, generated
source, test reports and failed counterfactuals retain a per-file hash manifest.
The local status/remote retrieval receipt is
`builder-stall-fix-local-status-v1.json`.

## Reproduction

From `jumpserve-back-end`:

```sh
python3 -B -m unittest discover -s research_workflow/tests
python3 -B research_workflow/tests/check_experiment_builder_linux.py --retained-paper
```

The native check needs the existing pinned local image/vendor preparation and
the already captured assessment files. It does not sign in, call a model or
provision a host. Its default mode retains the historical three-slot fixture.

From `jumpserve-infra`:

```sh
npm test -- --runInBand
npm run build
python3 -B bin/check-builder-stall-fix-local.py
python3 -B bin/record-builder-stall-fix-local.py
python3 -B bin/retain-builder-stall-4055396e.py --fix-validation
```

The last command appends private evidence only. It verifies AWS account
395567831870 and Supabase project regphejnlvfpyokpniny before storage/metadata
writes. The connected Supabase MCP points elsewhere and is not used.

## Remaining release work

An explicitly requested release must freeze and run bounded **live full-paper
model** qualification, verify the exact production AMD64 image, inspect actual
generated programs and decisions, and exercise candidate freezing, fresh reviews,
job creation and real measurement ingestion. Reused cases remain development
checks; broader autonomy needs held-out papers. A controlled experiment still
may yield honest inconclusive findings.

Only then approve the exact source/resource policy, commit/pin the new runtime
(including the new v2 cost file), merge/push and deploy under the existing release
procedure. Preserve original records, budget/deadline and unknown-call identities.
No schema or frontend change is required by these local fixes; no new browser or
authenticated chat check was performed in this turn.
