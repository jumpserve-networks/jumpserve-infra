# Research Verification production release, 2026-10-07

Released at https://jumpserve.quaint-lab.org/module/research-verification.
Start at `/module/research-verification/new-study` after Google sign-in. Intake
records metadata; source review, claim extraction and domain experiment design
remain substantive work. Only registered matched numerical checks run automatically.
Generic AI chat remains disabled pending evaluated prompts.

Amplify app d24jvguj7brnkj, main build 105 succeeded for frontend revision
bc6f87abb480c966dd56b828a60f5c279d8fc83f. Backend runtime is pinned to
d932544e0138d7449f23c5f6ee666a30b845fc1b. Infrastructure is archived on
`release/research-workflow-20261007` and deployed directly to the existing
JumpServeBenchmarkStack; unrelated agent/benchmark AMI releases were not triggered.
The benchmark AMI remained ami-0808d1157e26c65cb.

Targets 395567831870/us-east-1 and Supabase regphejnlvfpyokpniny were verified
before mutations. Both SQL migrations were applied. All 20 relations passed
production RLS/grant checks, including browser write denial, private originals
and service-only RPCs. The differently targeted Supabase connector was not used
for mutations. Apply receipts hash submitted bytes; catalog checks do not recover
originally executed SQL.

46 backend, 120 frontend and 84 infrastructure regressions pass; lint/builds pass.
Earlier actual isolated PostgreSQL concurrency/RLS and completed/missing/invalid
browser evidence is retained and reused on unchanged application bytes. Changed
hosting configuration received fresh infrastructure checks.

Both deployed Lambda archives were retrieved; all six runtime hashes match the
manifest. The live API rejected anonymous writes and a forged bearer. One actual
scheduled invocation processed two private synthetic controls: complete/partial
runs, four measurements, recorded zero, one missing value and discrepancy. Both
jobs await review; no assessment/publication was created. All four original
Supabase artifacts passed retrieved-byte hash verification. The setup used an
explicit trusted operator fixture identity, not a Google authentication account.

Five production browser groups pass: desktop/mobile navigation, empty results,
instructional queue states/downloads, light/dark layouts, missing study/export,
sign-in return paths and availability of the original completed IPv6 module.
No browser errors were captured. Primary AI inspected desktop/mobile screenshots;
no human, independent or held-out review is asserted. Worker-disabled text belongs
to the labelled instructional example; the live API reports workers enabled.

The first CloudFormation attempt failed and rolled back on the account's quota of
10 concurrent Lambda invocations. AWS rejected the minimum increase request; no
support case was opened. Production shares the existing pool, with no API/worker
reservations. PostgreSQL retains four global/two study queued jobs, resource locks
and fenced leases. See release amendment v2. Both deployment attempts are retained.

Failed verifier attempts are retained: local SDK credential resolution, incomplete
CloudFormation inventory and intake-link selector. Corrections used temporary CLI
credentials only in memory, complete pagination and the canonical route. They
do not establish released runtime defects or paper discrepancies. Scoped Git
attributes preserve original log bytes after detecting newline normalization.

Usage includes bounded CloudWatch REPORT samples, worker/run wall time and 10,951
original Supabase payload bytes. Lambda-reported memory is environment usage,
not measured per-job peak. AWS/Supabase/Amplify/Codex charges are unallocated;
missing cost/model usage is not zero. Empty filtered captures were preserved and
followed by bounded direct stream retrieval. No Bedrock or experiment EC2 work
was requested.

Conditional gaps: legitimate Google owner actions, cross-owner requests, provider
round trip, live expired-lease recovery, and a genuine completed generic study for
production-specific charts/CSV/JSON publication. Isolated PostgreSQL/browser checks
cover those data states and lease fencing. Synthetic science or fabricated reviews
were not published to fill gaps. Zero generic publications is a deliberate empty
state, not zero scientific claim coverage.

Scientific coverage is unchanged; previous IPv6 labels remain 3 reproduced,
3 discrepant, 5 inconclusive and 4 untested under their recorded conditions. This
release conducts no new paper experiments. See `research-workflow-release-v1.json`
and the original-byte manifest in `research-workflow-release-validation`.
