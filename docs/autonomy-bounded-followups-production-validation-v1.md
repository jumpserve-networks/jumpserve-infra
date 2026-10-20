# Bounded autonomy: production release validation

Production is active at https://jumpserve.quaint-lab.org. The explicitly requested
release was pushed to `main`, deployed, activated and checked on 2026-10-20 UTC.
The machine-readable companion records original evidence paths and SHA256 hashes.

The frontend is commit `7b8768198fb3970b120d92490b79a838a92e650e`, Amplify main job
117 (`SUCCEED` for build, deploy and verify). Backend commit
`85e41235c5a7864358561f5e6fb696939bf7099e` is pinned in runtime manifest v27.
Infrastructure application changes were committed in `0216551`; subsequent
verification corrections include `59cdadf` and `bedf3fa`. Later evidence-only
commits do not change deployed application bytes. Three deployed research Lambda
ZIPs match all 25 pinned runtime file hashes. The qualified bounded TCP function
is version 1 with 128 MB memory, five-second timeout and logs-only execution IAM.

Before production changes, the actual AWS account and Supabase Management API
project were verified as **395567831870** and **regphejnlvfpyokpniny**. The scoped
benchmark stack was deployed held, then activated after its cloud control passed.
The existing benchmark AMI remains `ami-0808d1157e26c65cb`. Unrelated all-stack and
AMI CI workflows were avoided. CloudFormation completed both updates.

Migrations `202610190001` through `202610190010` were applied as original bytes,
with per-migration hashes and receipts. Earlier guards and failed evaluations
remain in history. The published autonomy prompt is v8,
`20934b76-08d7-55e9-b101-1bed29db42a0`; other module prompt pointers were preserved.
The API reports `research-autonomy-v2`, enabled, with defaults of **$100 aggregate
conservative commitments per paper, seven days elapsed and 25 model attempts per
claim**. Evidence reads and failed calls consume attempts. Background polling is
enabled every minute, with two concurrent claims per paper and four globally.
There is no two-turn application limit.

Local verification passed 161 backend tests, 187 frontend tests, 93 infrastructure
tests with the actual backend checkout and zero skips, and eight trajectory-policy
tests: **449 total**. Frontend and infrastructure builds passed. Lint has no
errors and one pre-existing navigation warning. Eleven actual local Postgres
groups passed, including ownership/RLS, atomic shared budgets, 25-attempt and
seven-day stops, parallel leases, context recovery and rejected-call provenance.
The retained seven-group local browser campaign covers unchanged component
bytes; its authentication, provider and storage boundaries are fixtures.

Five production browser groups passed: four public entry/results pages; desktop
1365 and mobile 390 widths in light/dark themes; anonymous login return paths;
explicit missing public data and export 404; and the enabled v2 capability and
fixed limits. Four screenshots were retained. The primary implementing AI
visually inspected the mobile light and desktop dark screenshots, including the
archived chart, descriptive ranges and visible coverage limits. This was not
human review. Actual private queue and autonomy API requests without credentials
returned 401. Catalog checks retained RLS and browser write denial; both new
context-recovery RPCs remain service-only. The raw bucket remains private.

The actual production TCP control used study
`feeb23fe-dc51-42b0-9a51-7ded3ee4fa6e` and job/run
`0bea30f7-1c70-46ac-a33f-1dec657f701c`. One immutable Lambda invocation performed
two TCP loopback exchanges with a 32-byte payload and 2-ms application delay.
Supabase retained four recorded measurements: 32 received bytes for each
exchange and RTTs of 19.375607 and 2.211508 ms. These are correlated descriptive
observations on one host/process/connection, without an inferential interval.
They do not validate CDN behavior, Internet latency or any academic paper claim.
The queue correctly remains `awaiting-review`; the run is `complete`. No academic
assessment, publication, model call or EC2 instance was created by this control.

The initial control was rejected before queue admission because the test setup
omitted an applicable claim/check. The v2 correction verified the absence of any
job/run, preserved the original protocol/configuration and all identities, added
an explicitly scoped software-control source/claim/check, and resumed once. The
failed v1 report remains unchanged. Input, original synchronous Lambda output and
normalized output were downloaded from private Supabase Storage; all three
hashes and byte counts matched. Valid anonymous-key requests were denied. This
service-operator control does not exercise Google-authenticated browser launch
or the autonomous paper-budget admission path; those boundaries must not be
inferred from its success.

The separate actual Bedrock/controller/Postgres/arithmetic trajectory used the
unchanged v8 candidate for one retained IPv6 numerical claim. It used 25 total
attempts: 24 answers and one explicit throttle rejection. Five of six checks and
960 of 1,152 planned cells completed. The controller stopped at the declared
attempt limit and retained **inconclusive**. Three redundant inventory reads
consumed attempts. This release passes bounded safety, provenance and stop
criteria; it does not establish eventual scientific closure, improved general
accuracy or whole-paper validation. The other 14 paper claims were excluded.

All 24 raw structured/rendered answers and the rejection were reviewed by the
primary implementing AI, which was neither human nor independent. Cases were
exposed development/release checks, not held-out validation. An explicit throttle
at attempt 10 was reconciled once by the service operator in isolated SQL, with
the failed attempt, costs and original deadline retained; no uncertain call was
replayed. The subsequent call was numbered 11. This was not automatic production
recovery. Earlier failed criteria, the original two-turn observation, local
database-adapter failure and collector failure after the throttle remain archived.

The live trajectory retained all 25 prompts/outcomes, five runs and 960
measurements in its isolated database snapshot, whose SHA256 is
`1562544344ac59642899168c65321dc8f93bdd181007a51e600e7caa8d094ce0`.
Its $19.55 conservative commitments include orchestration; known token-based
estimates total $2.62, with one rejected call's usage missing. Including earlier
development work gives **45 unique provider attempts, 44 answers, $4.61 known
token-based estimates and $29 conservative commitments/reservations**. The new
cloud control has a one-cent per-invocation compute/request envelope, not a
measured charge. Actual invoices, hosting, orchestration and lifetime storage
charges are not independently measured or capped by that one-cent envelope.
Missing usage and unallocated costs are not zero.

The published private evaluation archive contains 925 files, 54,267,719 original
bytes and 15,553,980 compressed bytes. Its SHA256 is
`15f837a5313d3765062257a8be76119cd27a3e3bb45a6eefb775bc8b3fa64d90`.
Every archived member and the stored/retrieved archive bytes were hash-verified.
The additional production artifact manifest records deployment receipts, source
ZIPs, failed/successful controls, original data and browser screenshots separately.
Both archives are private, with readback verification and anonymous denial.

Remaining conditional gaps: no usable legitimate Google session was available
for a fresh authenticated browser planning/storage/launch request or chat. Local
fixture authentication is not represented as that check. Autonomous netem, EC2
and custom-package spending still needs independently enforced runner-specific
cost bounds; the bounded TCP policy does not authorize those runners. Released
code avoids the previous unbounded planning context, but cannot guarantee that
arbitrary claims become conclusive within finite resources. Scientific labels
and broader source-review limitations remain unchanged by this software release.

Read-only verification can be repeated from the respective repositories:

```bash
# jumpserve-infra: verifies exact deployed sources, access, capability and poll
python3 -B bin/autonomy-followup-release.py --mode verify
# jumpserve-front-end: no model calls, studies or experiments are submitted
node scripts/verify-autonomy-release.mjs --deployed
```

The cloud-control and archive commands are intentionally one-shot and retain
their identities. Do not rerun them to manufacture new evidence or overwrite a
failed receipt. Their original commands, amendment and outcomes are retained in
the companion report and private production archive.
