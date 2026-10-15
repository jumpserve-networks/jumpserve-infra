# Source-review amendment v2

Declared after the v9 main campaign and before the v10 follow-up. Preserve all
21 v9 attempts, original model classifications, server-rendered answers, exact
source values, runtime snapshots and AI judgments. Source values matched their
recorded paths, including the formerly inverted statistics field. However v9's
schema made every dependence classification blocking, and actual answers applied
that category to declared descriptive-only limitations. Two calls also failed at
the provider CLI; diagnostic stderr was not retained, so the cause is unknown.

V10 adds an explicit blocking/warning severity to the source classification.
Declared scope limitations can remain warnings; actual conflicting units,
invalid inferential claims and required missing inputs must still block. The
backend derives readiness from the declared severities without rewriting the
model's judgments. Source rendering stays verbatim, not model-authored prose.
The original correctness, source-fidelity and readiness criteria are unchanged.

One follow-up campaign: the same 21 frozen cases, one call/case, no automatic
retries, 2,048 output tokens/call, 24 KB research messages plus system/schema,
1,200-second total budget. Pace calls by at least three seconds and retain bounded
provider failure diagnostics/hashes; report missing usage as unknown. This pacing
does not establish the cause of earlier failures. No selectively repeated cases.
Further substantive failures require a new declared protocol; do not retry until
a desired result appears. Reused development cases and AI implementer inspection
are not independent, human or held-out validation. No production changes.
