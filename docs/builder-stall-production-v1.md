# Builder recovery release and verification

The release removes the recorded context/repair loops and the five-loss counter
admission conflict. All three declared live qualification cases passed; deployment
and its separate production verification are pending.
The final machine-readable deployment receipt is
`builder-stall-production-v1-status.json`; scientific coverage is reported
separately in the assessment queue.

## Scope and changes

The builder receives a bounded work packet, exact source-page reader, actual
implementation inventory and separately identified scheduling notices. Optional
material becomes an explicit hash-bound reference when the working view is full.
Complete source/context/history remain retained; the 72,000-byte native request
fence is unchanged. A repeated unchanged recovery stays blocked through the real
repair router. A changed executable adapter receives a targeted opportunity
without resetting commitments, elapsed time, claim identity or unknown calls.

The native execution contract now declares the exact metadata and dependency
lock schemas. Derived Python caches are retained separately, with original hashes
and an exclusion manifest; the executable package contains the source files.
Dependency directories, symlinks, unsupported cache contents and size violations
remain rejected. Repair tests execute the exact sealed source tree, rather than
potentially stale compiled code. The server execution wrapper is unchanged.

The netem-specific counter ceiling is 20,000,000,000 bytes. The unchanged formula
requires 18,760,000,000 bytes for five loss conditions at 100 Mbit/s for 30 seconds.
This is an aggregate interface-counter allowance, not billed Internet egress.
Other runners retain their 10 GB limits. The versioned cost policy preserves the
same t3.medium host, standard credits, 8 GiB root volume, one-instance limit,
1,800-second ceiling and conservative $1 reservation. Historical v1 remains
unchanged. Exact-source and cost-policy approvals are required before activation.

## Qualification and preserved failures

The exposed fixture uses the retained fictional manuscript **The Impact of Packet
Loss on TCP Throughput in Controlled Networks**, SNC-NEG-001. Its reported data
are explicitly fabricated. The PDF SHA256 is
`77becb203ef79c5e5d0b69ee9cfc5553e5680d2c44128aaa6b8f2c545d533617`.
The source-table calculation fixture is archived-data arithmetic; the namespace
TCP sweep produces new empirical software-qualification measurements. Neither
changes an assessment finding automatically.

All attempts and amendments remain retained:

1. The first native harness lacked its Dockerfile capture input. Its subsequent
   live precondition stopped before inference. The corrected bundle is separate.
2. Forty-two completed model calls produced a repaired file-path implementation
   and a dynamic source-arithmetic program. Independent ordinary, zero, null and
   changed-input controls passed. Packaging then rejected Python cache files.
3. A validation-only follow-up exposed extra fields in `build-evidence.json`.
   The builder interface had omitted its strict three-array schema.
4. A later metadata repair stopped before inference because its working packet
   exceeded 8 KB. The exact failing context now fits with a 7,463-byte packet and
   12,542-byte bootstrap, preserving complete context and history.
5. Four additional completed calls corrected the metadata while preserving the
   executable and dependency bytes. The model stored all original metadata bytes
   losslessly in a JSON/base64/SHA256 envelope. A direct-copy-only test incorrectly
   rejected that encoding. The corrected checker verifies strict decoding, exact
   original-byte equality, original and representation hashes, and separately
   retains the decoded raw bytes. Corrupt-byte/digest negative controls pass.
6. The final validation-only campaign reuses all **46 unique completed calls**;
   it does not replay inference. Its passed native controls are inherited only
   after verifying identical backend, fixture and production AMD64 image bytes.

The cumulative provider-call ceiling remains 48, with at most $48 in conservative
qualification reservations. A pre-acquisition amendment permits a bounded
follow-up phase within 90 minutes of the original freeze. This qualification
clock is separate from the paper authorization. The paper keeps its $1,000
ceiling, original November 4 deadline and no AI-turn cap. No netem measurement
preceded these amendments.

The actual provider-reported usage across the 46 calls is 459,420 input tokens,
6,780 output tokens, and 466,200 total tokens, with usage present for every call.
Subscription allocation, measured charges and unallocated host/storage charges
remain unknown. Reservations are not invoices. No paid API fallback or new cloud
instance is used by qualification.

The production image is
`sha256:542c0bd0a512d3c18348103775a983a840067eaadb703276e432c17cc5308c64`,
Linux AMD64. Earlier ARM64 synthetic-response checks remain distinct. Evaluator
and reviewer are the implementing Codex AI: not human, independent or held-out.
The source was already exposed and the harness was corrected after observed
failures. These results do not validate performance across unseen papers.

## Verification and scientific limits

391 backend tests passed, including the actual repair-router stagnation path,
source/page identity, dense working views, cache retention and exact resource
bounds. Infrastructure checks include 94 passing tests with five existing
conditional skips, TypeScript compilation, three metadata-decoder controls and
actual isolated Postgres builder/repair admission, persistence, RLS, budget,
immutability and reconciliation checks.

The declared live criteria require real generated programs, incident-bound repair
tests, portable execution using file paths and the unchanged server wrapper,
preserved zero/missing values, changed-input controls, and the complete loss grid:
0%, 1%, 2%, 5%, 10%; 100 Mbit/s; 20 ms delay in each direction; three 30-second
trials per condition. The implementation checks receiver byte/time/rate
consistency and retains original command outputs and missing observations.

The three sweeps share one existing host. Condition values and repeated trials
are dependent; descriptive results do not support a cross-host confidence
interval. Successful software execution does not establish the paper's 35%
claim, causal window/queue explanation, external-network validity or broader
generalization. Published arithmetic and new measurements stay distinct.

The completed qualification recorded 75/75 observations, with no missing,
invalid or ambiguous observations. All 15 receiver byte/time/rate calculations
passed a separate implementation check against the original iperf outputs.
Mean throughput at 0%, 1%, 2%, 5% and 10% loss was respectively 23.445, 2.972,
2.080, 1.186 and 0.681 Mbit/s. These are descriptive software-qualification
results on the existing worker, not a paper assessment or a confidence interval.
The review and all failed evaluations are saved separately in the prompt
evaluation tables. The final qualification archive SHA256 is
`71b179462f085cc61e59494454020668f04126f88b82b0dd48a19c0f74d5baa9`;
the passing review report SHA256 is
`d495d30bedaa3f715b757487742d853fd3ab169032cc817194d0ecb4ee395418`.

## Reproduction and deployment

From `jumpserve-back-end`:

```sh
python3 -B -m unittest discover -s research_workflow/tests
```

From `jumpserve-infra`:

```sh
npm test -- --runInBand
npm run build
npm run test:research:builder
npm run test:research:repair
python3 -B -m unittest discover -s test -p builder_preservation_check_test.py
python3 -B bin/check-builder-stall-fix-local.py
```

`bin/builder-stall-release.py` is a fixed-target release controller. Its frozen
campaigns, requests, original answers/checkpoints, failed runs and per-file
manifests live under the ignored `.test-artifacts/builder-stall-release-v1` and
private, hash-verified Supabase artifacts. Use `status`/`collect` on a dispatched
campaign; never replay `live`. Follow-up modes preserve original identities and
declare amendments before additional work. Actual native controls need the
retained images/vendor artifacts and the existing worker authorization.

After all declared cases and substantive inspection pass, the controller records
evaluations, approves only the exact source/resource policies, pins the clean
committed backend and stages it with `bin/prepare-research-runtime.py`. Scoped
`bin/openclaw-release.py` diff/deploy operations update the existing worker asset
and benchmark stack with admission held. Explicit SSM runtime installation keeps
the existing encrypted 300 GiB worker and its grant. Deployed-byte, executor,
RLS, public API and write-denial checks precede restoring admission/polling.

Public desktop/mobile queue inspection and sign-in return navigation are release
checks. Authenticated upload/confirmation/chat require a legitimate browser
session and are reported precisely when unavailable. Actual autonomous candidate,
review, job and measurement progress is observed separately; qualification
programs and Docker sweeps are not relabeled as owner-created queue jobs.
