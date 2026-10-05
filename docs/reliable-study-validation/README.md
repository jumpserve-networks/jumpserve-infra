# ReliableSketch release evidence

This is a limited scientific assessment. The original trace curves, FPGA/Tofino results, complete direct-source review, full theorem audit and operational generalization remain untested or inconclusive. The module reports these limits beside its results. Scientific discrepancies are retained findings, not software test failures. All recorded review was AI work by the study implementer; no independent human review occurred.

The experiment implementation, source inventory, frozen protocols and commands live in `jumpserve-back-end/experiments/reliable_sketch/README.md`. Public downloads at `/module/reliable-sketch-study/test-results` retain our generated input/raw CPU bytes and adapters, the four protocols, seven SQL migrations, source inventory, published values, all three chat evaluations and predeployment validation. Original publications and author artifacts remain in private Supabase Storage; `storage-manifest.json` and `release-storage-manifest.json` record retrieved member hashes.

The verified targets are AWS account `395567831870`, Supabase project `regphejnlvfpyokpniny` and the existing `JumpServeAgentStack`. No experimental cloud instances were created. Frontend deployment uses the existing Amplify app `d24jvguj7brnkj`, branch `main`, serving `https://jumpserve.quaint-lab.org`.

Recheck from the infrastructure repository:

```sh
npm run test:agent
PROMPT_TEST_DATABASE_URL=postgresql:///jumpserve_prompt_test npm run test:agent:database
npm run build
python3 bin/reliable-study-database.py --verify
```

Recheck from the frontend repository:

```sh
npm test
npm run lint
npm run build
node scripts/verify-reliable-study.mjs https://jumpserve.quaint-lab.org
```

The database test requires the local disposable PostgreSQL test database. Production import and storage scripts obtain credentials through the existing keychain/AWS architecture, verify both targets, and never expose service credentials to browser code. The fixed `--record-release` operation preserves the original production validation JSON in the private artifact table, retrieves and hashes it, then publishes its parsed status through `reliable_study_meta` and `/module/reliable-sketch-study/api/release`. A changed existing record is refused; later corrections need a new version.

Chat development evaluations v1 and v2 failed and remain retained. The frozen v3 protocol distinguishes ten reused development regressions from two fresh held-out cases. Candidate `reliable-evidence-v2` passed all twelve declared answer contracts and actual-answer secondary AI inspection. One contradictory advisory same-model grader judgment was preserved and explicitly adjudicated by the secondary AI reviewer. The implementer/reviewer and model judge are not independent human validation. Prompt publication guards check this declared protocol and report; a successful unit test does not establish empirical answer reliability.

`predeployment.json` records local release blockers. `browser-production-v1.json` preserves the first production failure: bibliography text overflowed a 390px viewport. Its separately committed correction changes wrapping only. `production-validation-v1.json` records the corrected deployment, production browser/export checks, available usage and remaining conditional gaps. The final public release API is the current status; the archive's before-deployment JSON is a preserved historical snapshot.

An actual Google-authenticated browser-to-agent request remains conditional because no legitimate session was available. Direct saved-prompt model calls, unit tests and the deployed unauthenticated 401 response do not substitute for that end-to-end check. Billing reconciliation, local workstation/power allocation, hosting/build charges and Codex orchestration usage are unavailable, not zero. Available model estimates retain failures whose usage was returned and separately identify failures with no usage.
