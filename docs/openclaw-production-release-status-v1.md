OpenClaw is deployed and active at https://jumpserve.quaint-lab.org. Backend
`38e501c`, frontend `823138b` and the scoped infrastructure release are on main.
Amplify job 119 succeeded. Runtime manifest 34 matches all 31 files in the
deployed API, autonomy controller, numerical worker and private OpenClaw host.
The active v10 prompt and its original passing evaluation remain unchanged;
failed v9 and subsequent controller follow-up evidence remain retained.

The AWS host uses its own native ChatGPT authorization with OpenClaw 2026.10.5,
Node 24.16.0 and `gpt-6.1-sol`. Actual native refresh, model availability and
inference were verified. Autonomous assessment has no API-key or Bedrock
fallback. Defaults are $100 in conservative paper commitments, seven elapsed
days and no AI turn-count ceiling. Two claim slots per paper and four globally
remain enforced. Private data retains RLS and browser write denial.

An actual authenticated production PDF submission persisted 66 real model turns,
six archived arithmetic experiments and 1,152 percentage cells. Original prompt,
response and native/provider artifact hashes verify after retrieval. The first
57 calls and four experiments remain unchanged. A premature assessment pause
was demonstrated with exact-answer replay, corrected, tested and deployed.
Audited continuation added nine calls and the two remaining frozen checks without
resetting counters, commitments or the deadline. The claim happened to resolve
on turn 25; that is not an application limit. A separate actual SQL fixture
verified continuation beyond 25 to 40 reserved turns.

The folded-metrics claim is reproduced under its archived, matched conditions.
A separate deterministic checker confirms all 1,152 values, units, identifiers,
published references, bounds, differences and original tolerances. It shares
the frozen inputs and implementer; it does not independently validate the source
measurements. Fourteen other claims remain untested in this autonomous control,
with their external requirements visible. The fifteen earlier imported
assessments remain unchanged. This is not whole-paper validation, new Internet
measurement, raw-pcap reproduction, causal identification or generalization.
Descriptive counts do not support a confidence interval here.

Validation includes 187 backend tests, 199 frontend tests, 95 infrastructure
tests with the backend contract, TypeScript/Next builds, SQL upgrade/security/
dispatch/continuation checks and exact-answer replay. Five public production
browser groups passed. A legitimate signed-in browser verified PDF intake,
saved prompt/response pagination, final claim status and desktop/mobile layouts
and themes. A new classic ChatPanel request and fresh networking experiments
were not exercised in this release campaign. Review was performed by the AI
implementer and is not human or independent review.

The paper control used 645,161 reported tokens and $74.71 in conservative
commitments. Actual charges, subscription allocation, infrastructure and storage
cost allocation remain unknown. All 95 live model calls for this release,
including rejected-candidate evaluation, are distinguished in the JSON report.

The machine-readable [release status](openclaw-production-release-status-v1.json)
links report hashes, private archive manifests, deployment receipts and retained
failures. [Claim coverage](openclaw-production-claim-coverage-v1.json),
[controller validation](openclaw-production-controller-validation-v1.json),
[exact-answer replay](openclaw-production-partial-replay-v1.json),
[authenticated results](openclaw-production-authenticated-result-v1.json),
[arithmetic verification](openclaw-production-arithmetic-v1.json) and
[browser evidence](openclaw-production-authenticated-browser-v1.json) separate
software release readiness from scientific coverage.

Reproduction commands, from jumpserve-infra:

```sh
python3 -B bin/check-openclaw-partial-replay.py
python3 -B test/check_autonomy_partial_database.py
npm run test:research:autonomy
JUMPSERVE_BACKEND_CHECKOUT=../jumpserve-back-end npm test -- --runInBand
node bin/verify-openclaw-browser.mjs
python3 -B bin/openclaw-release.py verify
python3 -B bin/openclaw-study-verify.py observe --study 5ef8e6bd-e3ff-4ba9-8427-d25fb525fb74
python3 -B bin/check-openclaw-arithmetic.py --snapshot .test-artifacts/openclaw-study-verification/20261021T193747389974Z/private-snapshot.json
```

The first replay requires the preserved private snapshot and original controller
bytes, whose exact hashes are declared by the script. The SQL tests require the
isolated local PostgreSQL service. Production inspection requires legitimate AWS
and Supabase access. These commands do not replay an uncertain model call or
reset a study. See the original release protocol and amendment v6 for the
predeclared criteria, bounds and follow-up scope. Approval delays caused late
administrative observations; the reports retain actual recorded event times
and observation times separately.
