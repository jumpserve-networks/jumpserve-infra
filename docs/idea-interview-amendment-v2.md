# Interview amendment v2

Declared after the first sixteen-call development campaign and before the v4
follow-up. Preserve protocol v1, candidate v3, its original runtime snapshot,
all sixteen actual responses, and the four failed interview judgments.

Four inspected interview answers failed: a known unit was re-asked alongside a
different field; feature selection was mapped to inputs; an unsupported pilot
confidence interval was suggested; and unknown cost was invented as a blocker
and mapped to an observation count. Candidate v4 adds explicit single-field
routing, known-answer reuse, dependence/uncertainty and bounded-pilot cost rules.

Run the same sixteen frozen cases once for v4 with the original 24 KB input,
2,048 output tokens/call, zero automatic retries and 900-second campaign limit.
Maximum additional calls: sixteen. These are reused development regressions,
exposed to prompt tuning, not independent or held-out validation. All original
schema and substantive criteria must pass. Record reviewer identity, original
responses/runtime snapshots, token usage, elapsed time, failed calls and unknown
charges. Neither draft is published by this campaign.

The first browser campaign also exposed an attempted change to immutable input
provenance. Correct the implementation by reading the validated routing field
from the preserved original provider response. Retain immutable request metadata
and the existing database guard; do not relax that guard. Repeat the fixed local
browser campaign after this correction. Synthetic model tests remain distinct
from actual-answer evaluation.
