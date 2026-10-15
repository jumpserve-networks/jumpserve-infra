# Interview amendment v4 — explicit task prompt selection

Frozen after v5 inspection, before v6 evaluation. Preserve all earlier candidate
bytes, responses and judgments. V5 still fails three cases: an unnecessary
readiness question for the complete plan, speculative technical commentary in
the injection review, and a metrics question that also asks provider population.

The implementation sent both interview and review instructions to every task.
This is an avoidable ambiguity. The observations do not establish which clause
caused each answer. V6 stores a versioned JSON template in the existing prompt
table. The backend selects only the review or interview system text before the
call; the selected system text/hash and full stored prompt hash are retained.
Reviews receive no interview instructions. Review output should focus on actual
packet conflicts rather than speculative explanations. Interview text explicitly
restricts each question to one destination field.

Run the same sixteen frozen development cases once, maximum sixteen additional
calls, 2,048 output tokens, 24 KB research messages, 900 seconds, no automatic
retries. The versioned system template and formatting schema are additional
recorded input. All sixteen substantive criteria remain publication blocking.
This is reused/tuned development evidence, not independent validation. No
production publication or deployment is authorized or performed.
