# Evidence-reference verifier correction, v11

The single lossless-packet call returned a phase-correct inconclusive answer with
full-claim coverage false. Preserve its original report, including the failed
reference check. That check admitted only measurement IDs and run IDs, whereas
the supplied recorded evidence also explicitly contains a campaign ID, input
hash, output hash and derived complete-record-set hash. Every returned reference
maps to those exact structured fields; none is fabricated.

Before reviewing a corrected report, freeze the reference correction: admit only
actual record IDs and hashes in the current runs, selected campaign/protocol/input
and verified decoded record-set. Never admit arbitrary strings or identifiers
appearing only in prior model answers. Record the exact JSON field path for each
reference and retain the original false-negative report. No new provider call,
answer editing, relaxed scientific coverage rule or substituted numerical value.
Model reference formatting remains a limitation: the controller, not a bare model
hash list, constructs the final typed assessment evidence.

The composite publication evidence now has nineteen component answers: sixteen
frozen model cases, two index/review integration cases and the one packet case.
Keep all original component reports and separately record the corrected verifier
judgment, source hashes and released builder revision. The v10 ceilings, one-time
same-run recovery, two-paper limit and scientific criteria are unchanged.
