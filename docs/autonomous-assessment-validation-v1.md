# Autonomous assessment implementation and validation

Implemented locally on 2026-10-18. Application defaults are **USD 100 per paper,
seven elapsed days and 25 model invocations per claim**, including invalid and
failed responses. Work is admitted under conservative spending commitments;
measured cloud invoice charges are not available. Parallelism is two tasks per
paper and four globally.

One authenticated form submission atomically retains the paper and exact initial
request. The background controller prepares supported sources, creates separate
claim tasks, requests two fresh AI reviews, freezes applicable checks and queues
registered execution. Specific failures feed subsequent prompts. External input,
equipment, authorization, implementation and pricing blockers stop the affected
claim while other admitted tasks continue. Closing the browser does not stop work.
Every dispatched effective prompt is persisted before its provider call; responses,
usage, unknown costs, failed attempts and evidence identities remain recorded.
Experiment Queue exposes this history, execution status and scientific findings.

Local verification passed 140 backend tests, 186 frontend tests and 91
infrastructure tests. Eight actual isolated PostgreSQL check groups exercise
budget races, leases, parallel admission, attempt/deadline limits, immutable
history, ownership/RLS, PDF extraction and the controller-to-arithmetic-worker
flow. Frontend and infrastructure builds pass. Frontend lint has zero errors and
one pre-existing warning in `auth-button.tsx:153`.

The browser campaign uses the actual components, API, PostgreSQL functions,
controller and arithmetic worker, with explicit synthetic authentication,
paper/provider responses and local Storage. It exercises submission, background
progress with the page closed, personalized follow-up, exact prompt history,
missing-equipment blockers, desktop/mobile light/dark layouts, actual Next.js
anonymous route/sign-in redirects and invalid/unavailable status responses.
The SQL/browser fixture's reproduced and discrepant labels concern synthetic
matched numbers; **they are not findings about an academic paper**. Date/deadline
checks use a declared isolated clock fixture rather than waiting seven days.

Review was performed by the primary Codex AI implementer and is not independent
or human review. Tests are development regressions, including reused cases. Earlier
failed runs and original reports are retained in the adjacent evidence directory.
Corrections include a trigger field-reference error, primary-key/order lookups,
SQL alias ambiguity in expired-work cleanup, and a browser verifier that selected
a task from another fixture study. Those failures are software/harness findings.

Numerical assessments require matched source, configuration, observation, metric
and unit identities, complete planned counts, two retained reviews and an original
frozen tolerance. Decimal arithmetic independently checks the recorded cells.
An interpretation disagreement reuses the same evidence. Earlier valid comparable
discrepancies cannot be erased by a later agreement; partial/failed runs remain
referenced separately. These checks share recorded inputs and implementation
assumptions and do not establish correctness, causality or generalization.

Production readiness remains conditional. No migrations, prompt publications or
application/infrastructure changes were applied to production during this work.
The fourteen-case live model development evaluation, actual answer review, real
Google-authenticated API/Storage flow and networking acquisition/cleanup have not
been verified. No live model calls or cloud test instances were used. Actual
charges and shared local compute/storage costs are unknown, not zero.

The new prompt remains an unpublished candidate. Autonomous cloud execution is
blocked because the shipped exact-specification cost-envelope catalog is empty;
hard network resource bounds must be validated before adding an envelope. Broader
claims need applicable domain assessors, and inaccessible/visual/supplementary
evidence remains uncovered. Inconclusive and untested are retained honestly.

See [implementation and reproduction commands](autonomous-assessments.md), the
[original protocol](autonomous-assessment-protocol-v1.md), the
[machine-readable validation record](autonomous-assessment-validation-v1.json)
and [artifact manifest](autonomous-assessment-validation-v1/manifest.json).
