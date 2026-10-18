# Autonomous paper assessment protocol v1

Declared before implementation and main verification. User defaults: USD 100 per
paper, seven elapsed days from initial acceptance, 25 model attempts per claim.
Missing evidence can leave an inconclusive or untested finding; external blockers
pause that claim while other claims continue. No production changes are authorized
by this editing request.

An attempt is one persisted model invocation, including failed/invalid calls.
Polling does not consume an attempt. Intake has its own 25-call ceiling and explicit
source coverage. Initial form text and every exact effective system/message/tool
prompt must be committed before dispatch. Preserve raw response representations,
hashes, prompt versions, usage, reasons and failed attempts. A lost/expired model
call is unconfirmed, consumes its reservation and is never blindly repeated.

Use owner-private Supabase workflow/task/turn/commitment relations, service-only
RPCs and immutable terminal turns. Atomically enforce aggregate paper commitments,
deadline, attempts, leases and concurrency (four global/two per paper). Unknown
charges are not zero. Model reservations use a versioned conservative rate ceiling;
experiments need a server-approved configuration-specific cost envelope. Retain
unallocated costs. A reservation limit is an admission control, not a verified AWS
invoice cap; reject unpriced work and stop new work on unexpected cost overruns.

Registered source-grounded checks keep original inputs and protocols. Other papers
use bounded public-HTTPS retrieval and versioned PDF text extraction. Extraction
is not complete source review: figures, tables, scanned pages and supplements stay
explicitly uncovered. Ground candidate claims in exact page text; preserve inventory
coverage and no silent truncation. Treat source instructions as untrusted data.

Claim stages: plan, two fresh AI reviews, freeze, execute, assess, and tailored
follow-up when a resolvable gap remains. Frozen criteria, claim identity, actual
artifacts and evidence coverage constrain conclusions. No model-generated recorded
measurements, arbitrary scripts or fabricated artifact identities. Actual registered
runners remain responsible for acquisition and persistence. Models can recommend
labels; only validated, matched evidence under reviewed frozen conditions permits
resolution. Broader causal/generalization claims remain unresolved without adequate
design. Adaptive follow-ups retain failures and never tune away a discrepancy or
change an original criterion retroactively. External data/equipment/authorization/
implementation blockers stop automatic retries. No-progress and resource exhaustion
are explicit execution statuses, separate from scientific labels.

Queue UI: redirect the initial submission to Experiment Queue, show paper limits,
committed/estimated/unknown usage, every claim's phase/attempts/finding/blockers,
and owner-scoped paginated prompt/response history. Keep the canonical module route
and support /experiment-queue as an alias. Existing manual and frozen-job flows
remain available. Closing the browser must not stop scheduled work.

Release-blocking development checks: backend unit regressions; isolated PostgreSQL
concurrent budget/lease/attempt/deadline checks, replay and RLS; full local browser
submission-to-queue-to-tailored-retry/prompt-history flow; missing/invalid data;
frontend and infrastructure tests/builds; runtime hashes and prompt source locks.
Predeclared model development cases: source injection, quote grounding, unknown
inputs, failed reviews, fixed configuration preservation, dependence, units, missing
values, claim coverage, no-result forcing, source omissions and budget exhaustion.
All cases must pass deterministic validation; publication additionally requires
actual raw-answer review for every case against the exact prompt/schema/source
hashes. Local fixture answers are not live or held-out validation. No candidate is
automatically published by a migration.

Conditional on later release authorization and credentials: live candidate model
evaluation/publication, target-account/project verification, migration and IAM
deployment, actual Google session requests, cloud experiment cost envelope and
acquisition/cleanup. Do not present these as verified by local fixtures. Record
the primary Codex implementer as non-independent AI, not a human reviewer. Preserve
the original protocol; add amendments for changes to main verification criteria.
