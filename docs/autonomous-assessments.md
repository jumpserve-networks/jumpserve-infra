# Autonomous paper assessments

Submitting `/research-verification/new-study` atomically saves a private paper and
its initial request. It opens Experiment Queue; `/experiment-queue` redirects to
the canonical module route and preserves queries. Closing the browser does not
stop enabled background workers. Defaults are USD 100 per paper, seven elapsed
days from acceptance, and 25 model invocations per claim, including failed and
invalid responses. Polling is separate from a model attempt.

The background controller processes source intake and then independent claim
tasks. SQL admission allows four concurrent tasks globally and two per paper.
Each claim plans a check, receives fresh comprehension and critic reviews, freezes
its applicable protocol, executes registered work and assesses actual evidence.
Unresolved results feed a new prompt with the specific claim, previous findings,
recorded outcomes and remaining resources. Repeated unchanged designs stop as
no progress. Unavailable data, equipment, permission, implementation or pricing
pauses that claim and exposes the exact requirement in the queue.

Execution status and scientific label are distinct. Inconclusive and untested
remain valid findings. A model recommendation alone cannot create a conclusive
assessment. The current automatic assessor handles complete, matched recorded
numerical cells with declared metrics/counts and an original frozen tolerance,
two retained reviews and consistent source/configuration/observation/unit identity.
It independently recomputes differences using Decimal. New networking pilots can
collect observations through existing runners but cannot automatically settle a
broader paper claim. Other scientific decisions need an applicable domain assessor.
No new study is automatically published to anonymous visitors.

Interpretation disagreements retry assessment against the same retained evidence,
without launching replacement experiments. Earlier valid comparable discrepancies
remain in the decision; partial/failed and other-method runs stay referenced with
separate coverage counts. Evidence uses typed record references compatible with
the existing workspace. The older queue's job-review ledger remains separate from
the autonomous claim assessment; no manual audit or human review is fabricated.

## Persistence and resource controls

Migration `202610180002` adds owner-private workflow, task, turn, commitment and
event relations. RLS remains enabled, browser reads/writes and RPC execution are
denied, and authenticated APIs verify ownership before returning records. A
background worker uses the owner's durable initial authorization, without storing
or refreshing Google session tokens or pretending the worker is a human reviewer.

Every effective system/message/tool/configuration prompt is stored before its
provider call, with original canonical request text, JSON, hash, prompt version,
model and reserved resources. Raw SDK response representations, hashes, parsed
answers, available token usage and failures remain retained. Original HTTP bytes
from the provider SDK are unavailable and are not claimed. Terminal turns and
original prompts are immutable. History is paginated ten turns at a time for a
selected owner/task; bulk queue polling does not retrieve all prompts. Source
originals and parsed artifacts use the existing hash-verified private Storage
path. Readable bytes or a verified hash do not establish complete source review.

Budgets are enforced on aggregate conservative commitments under one short SQL
lock before dispatch. Reservations are never silently released when charges are
unknown: an initial USD 5 overhead hold, USD 0.05 per bounded controller slot,
model price ceilings, and configuration-specific experiment ceilings. Actual
controller wall time and configured hosting memory are recorded when available;
actual invoice, shared hosting, database and Storage charges remain unallocated.
The USD 100 admission limit is not an independently verified cloud invoice cap.

Model pricing has a recorded version, source URLs and expiry; stale/unpriced
models cannot run. No discount or zero-cost assumption is used. Quotes for cloud
experiments are server-owned and bind the exact specification hash, expiry and
verified hard resource bounds. The shipped cloud quote catalog is empty: earlier
built-in runners do not establish a hard network-byte cap, so their autonomous
cloud spending is blocked until a valid envelope is supplied. Existing manual
networking tools are unchanged. Worker/queue admission also requires enough time
for the requested execution and cleanup before the paper deadline. Expired or
lost provider calls become unknown/blocked and are never blindly repeated.

Registered paper manifests retain original sources, protocols, input bytes and
previous findings. Other papers use public HTTPS retrieval pinned to validated
public IP addresses, bounded redirects/bytes/time and a subprocess with a pinned
PDF parser. Credential-bearing URLs, private/reserved addresses and arbitrary
commands are rejected. Candidate claims must be exact quotes from the supplied
page chunk. PDF text extraction is not figure/table/equation/scan/supplement review.
Limits of 10 MB, 300 pages, two million extracted characters, 25 intake model calls
and 200 admitted claims are explicit coverage bounds. Additional candidates and
their raw responses are retained; incomplete coverage cannot become a completed
full-paper validation. References are not recursively expanded by this controller.

## Local setup and verification

```sh
# jumpserve-infra; use the documented sibling backend checkout
python3 -B bin/prepare-research-runtime.py
python3 -B bin/prepare-autonomy-runtime.py
env JUMPSERVE_BACKEND_CHECKOUT=../jumpserve-back-end npm test -- --runInBand
npm run build
# Dedicated isolated PostgreSQL is required on 127.0.0.1:54477.
python3 -B test/check_autonomy_database.py
python3 -B test/serve_autonomy_fixture.py
# jumpserve-front-end, separate terminal; port 6002 is temporary verification only
npm test
npm run lint
npm run build
npm start -- --hostname 127.0.0.1 --port 6002
node scripts/verify-research-autonomy.mjs
# jumpserve-back-end
python3 -B -m unittest discover -s research_workflow/tests
```

The PDF layer is built from a hash-locked original pure-Python wheel. Its complete
file inventory is validated before synthesis; bytecode and undeclared files cannot
enter the layer. The queue fixture uses actual components, API code, PostgreSQL
functions, controller logic and the numerical worker, with explicit synthetic
source/auth/provider/Storage boundaries. It is not a real model or cloud experiment.

## Production activation

The current explicit release request authorizes this activation. Migrations
`202610180003` through `202610180017` preserve each candidate and additive
publication guard in the existing Supabase prompt tables. They do not themselves
publish or activate a candidate. Fourteen development cases, their full input
contexts, pass criteria, schema and implementation hashes are locked under `test/`.
Exposed/tuned cases are not held-out validation. Synthetic local publication-guard
declarations are clearly identified as fixtures and cannot establish actual model
evaluation. Evaluator/reviewer identities and AI/human status must be recorded.

Release operations verify AWS 395567831870 and Supabase
regphejnlvfpyokpniny, pass the declared local checks, perform and retain actual
candidate answer evaluation/review, apply migrations in order and publish only a
passing exact candidate. Runtime version 23 pins backend commit
`135184d13c7b4363ca9db9d5d640e5c3434fa0b6`. The v6 prompt uses versioned typed
issue codes, per-phase schemas and Opus 4.6. The first production positive control
exposed wrong-phase responses and an oversized selection context after the v5
fourteen-case campaign passed. That publication and all original failures remain.
The corrective evidence combines sixteen frozen saved-context model cases,
two separately frozen actual-builder integration cases and one separately frozen
complete-record assessment case. Component source hashes
remain separate; the integration lock pins the released context builder. Every
candidate is preserved, including five original throttled calls with unknown
charges. See release amendments v2–v11; none of these exposed development cases
is held-out, independent or human validation.

Selection indexes preserve every retained check/configuration identity and full
protocol hash. Fresh reviews receive the full selected conditions. Wrong-phase
answers remain invalid numbered turns and get specific protocol-error feedback;
unknown provider outcomes are not replayed. Neither indexing nor correction
changes a scientific condition or establishes complete claim coverage.

Assessment transports every original measurement field in a reversible columnar
packet with common values, explicitly indexed dictionaries and duplicate detail
fields factored once. Decoding must reproduce the original canonical record hash.
No rows, value strings, nulls, zeros, statuses or identifiers are sampled or rounded.
The 192-record production control fits an 86,304-byte request without raising the
96 KB/1000-record limits. Source rows and raw artifacts remain unchanged. The
separate packet verifier initially rejected real campaign/input/output hashes;
that false negative and its structured-field correction remain preserved.

Set `researchAutonomyEnabled=true` only with the durable queue enabled, stage the
verified PDF layer, deploy API/controller before the frontend, then verify a real
Google-authenticated request and private Storage round trip. Approve and validate
an applicable cloud cost envelope before testing actual networking acquisition,
normalized data, original artifacts and machine cleanup. These conditional checks
are not satisfied by the local fixture suite.
