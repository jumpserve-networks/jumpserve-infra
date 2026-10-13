# Research preparation verification protocol v1

Frozen before the main verification campaign on 2026-10-07. This is a software
development protocol; its cases are exposed to the implementer and are not held
out. Reviewer: primary Codex AI implementer, not independent or human review.

Question: can an owning researcher move a metadata draft through a retained
source-grounded plan, frozen protocols, campaigns and an interrupted/resumed queue
without losing originals, duplicating jobs, crossing owners or inventing evidence?

Release blockers:

1. Backend regressions must reject mismatched paper identities, missing claim
   coverage, cycles, unregistered automatic adapters and input overrides. Original
   manifest bytes and rebound input hashes must agree with the retained artifacts.
2. In an isolated PostgreSQL 17 database, apply all three workflow migrations.
   Execute actual preparation, scheduler and worker implementations against that
   database, with a clearly identified local Storage transport fixture. Verify
   owner-only preparation, atomic rollback, concurrent idempotent preparation,
   resumable queueing, private immutable plans and browser RPC/write denial.
3. Execute all six registered IPv6 numerical panels through those actual workers.
   Expect six complete runs, 1,152 matched cells, retained separate published and
   observed values, no missing/invalid/excluded cells and no new assessments.
   These are archived-value rechecks under the previously exposed 0.0051
   percentage-point rule, not independent reproduction or Internet measurements.
   Scientific disagreement must be recorded, not treated as software failure;
   the blocker is correct retention, identity and interpretation of the outcome.
4. Frontend regressions must exercise prepare -> enqueue, stopping on a failed
   request, preserving explicit coverage, and resuming only absent job IDs. A
   successful HTTP response alone cannot establish that the requested job exists.
5. Run backend tests, infrastructure type/build and route tests, frontend tests,
   lint and build. Inspect desktop/mobile browser states, including public missing
   data, uploaded-plan guidance, navigation and sign-in return paths. Distinguish
   fixture-browser verification from a legitimate Google-authenticated request.

Conditional checks before a production release: exact AWS account
395567831870 and Supabase project regphejnlvfpyokpniny; remote private Storage
round-trip; actual owner request with a legitimate session; deployed scheduled
workers. No deployment or production mutation is part of this local campaign.

Controls: synthetic small plans with deliberate missing dependencies, changed
identity/units, failed uploads and partial queueing; both anon and authenticated
database roles; a second owning identity; concurrent clients. Synthetic identities
exercise local authorization logic and do not impersonate a Google session.

Bounds: uploaded original JSON <=250,000 bytes; registered manifest <=1,500,000;
compiled artifact <=4,000,000; 1–100 campaigns; <=500 initial records; <=1,000
observations and <=10 seconds per prepared numerical job. Existing queue caps
remain four global and two per study; manual tasks are never claimed by workers.
Main tests stop on assertion failure and retain timestamped reports and database;
corrected follow-ups must retain the failed report. No model calls are required.

Metrics: case counts and Boolean invariants, actual cells/jobs/runs, hashes, byte
counts, monotonic wall seconds and available usage. No inferential intervals are
appropriate for this fixed, exposed development census. Missing charges and
model usage remain null; they are not measured zero. Local costs are unallocated.

Exploratory history: a compatibility pilot compiled and ran six panels locally
(1,152 cells); it did not persist a database campaign. A first generated manifest
exceeded the 1.5 MB cap and was rejected. Duplicate protocol configuration prose
was reduced while preserving all original configuration records; the cap was not
increased. These pilots are not independent validation.
