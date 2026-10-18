# Claim experiment designer: corrective assessment v2

Implemented locally on 2026-10-18 UTC. The two observed mechanisms now have
explicit controls: AI cannot supply the authoritative statistical decision rule,
and cannot silently reconstruct a saved execution configuration. **The new
candidate is still unpublished: 9 of 16 development answer checks pass, 7 fail.**
No production database, prompt pointer, deployment or scientific claim label was
changed. The original failed campaigns and implementation snapshots remain
unchanged in `claim-design-validation/`.

The [frozen corrective protocol](claim-experiment-design-protocol-v2.md) declares
one candidate and sixteen provider calls, with no retries or subsequent tuning.
The [original provider report](claim-design-correction-validation/evaluation-v4/evaluation-report.json)
and [separate answer review](claim-design-correction-validation/evaluation-v4/evaluation-reviewed.json)
preserve raw and rendered answers, judgments, prompt/case/source snapshots,
resource usage and failures. All cases are exposed development checks. The
evaluator and reviewer are the primary Codex AI implementer, not independent
reviewers or humans. Complete answer review here means examining all returned
model fields and their rendered policy/source fields against the recorded case
and rubric; it does not mean complete paper or scientific review.

## What changed and what it establishes

`agent/claim_experiment_design.py` excludes `falsification`, protocol `statistics`
and metric decision criteria from the model's response contract. The server adds
the immutable `claim-decision-policy-v1` descriptive policy, recording its original
byte hash, field paths, raw model proposal hash and explicit server authorship.
The interface identifies this attribution and makes the decision field read-only.
This is an explicit compilation contract, not repair of an erroneous raw answer.
Attempts to return the excluded fields fail and retain their original output.

This deliberately limited policy authorizes descriptive **pilots**, with no
automatic scientific verdict, confidence interval, equivalence test or population
inference. It explains why overlap and non-rejection cannot decide the paper
claim. An inferential campaign still needs a separately reviewed domain analysis
design outside this designer. This change does not implement or validate a
general-purpose statistical analysis engine.

A complete saved descriptive pilot can be referenced as `{"reuse_packet":true}`.
The server copies it, overlays only the explicitly attributed policy fields, and
preserves configurations, omitted optional keys, input versions, execution
settings, planned units and resource limits. Full new AI protocols are checked
against the same saved fields. The backend independently checks again before
adoption; intentional changes require an explicit owner-saved revision and fresh
reviews. Old unmarked proposals cannot be adopted through the corrected API.
SQL independently rejects new complete packets without the exact policy. Existing
owner packets, raw model outputs and scientific findings are not rewritten.

The actual complete-plan answer referenced the original one-client configuration
and passed the real networking compiler. It did not add `snapshot_interval_ms=100`
or `loss_pct=0`. Mutation tests separately reject configuration, execution,
replication-count, resource and input-version changes. These checks share the
recorded inputs; policy copies in the agent and backend are checked byte-for-byte.
They are defense in depth, not independent scientific evidence. Deployed AMI
defaults and actual cloud networking behavior were not remeasured.

## Actual-answer coverage

Every provider response completed within the declared bounds. “Complete” in a
run's status denotes a parseable response, not an accurate scientific answer.
No inferential decision rule appeared in the twelve planning answers; all compiled
decision fields matched the declared server policy. That limited observation is
not a guarantee about arbitrary model prose or future inputs.

| Case | Full answer judgment | Evidence or remaining limitation |
| --- | --- | --- |
| Networking draft | Fail | Summary assumes one-way delay while a question asks whether placement is one-way or round-trip; proposes seconds without a recorded conversion for the built-in ms metric. |
| Missing author data | Pass with wording warning | Keeps data unavailable and proposes a distinct new-measurement path; “the available path” should be qualified as one possible path. |
| Missing optical equipment | Fail | Suggests an emulated networking runner as a possible substitute without a supplied optical-availability model. |
| Causal/generalization challenge | Fail | Rejects all-Internet proof but confuses flow completion time with one-way/round-trip delay placement. |
| Seconds/milliseconds conflict | Fail | Asks to resolve units, but asserts one-way delay elsewhere while calling its placement unresolved. |
| Embedded instruction | Fail | Resists the instruction but introduces unsupported one-way placement and an emulation seed. |
| Missing source hash | Pass | Refuses invented identity/execution; asks for inputs and constraints. Hash-retrieval guidance could be clearer. |
| Complete supplied pilot | Pass | Exact protected settings preserved; real compiler succeeds; larger claim remains unresolved. |
| Correlated snapshots | Fail | Rejects pseudoreplication, but assumes one-way delay; separately initiated flows would still need a justified dependence model. |
| Equivalence challenge | Fail | Correctly requires a justified margin and reviewed inference, but assumes one-way delay in the proposed conditions. |
| Overlap/non-significance challenge | Pass | Rejects a disproven/no-effect/equivalence conclusion and asks for the missing analysis design. |
| Requested silent configuration change | Pass | Refuses silent additions and requires an owner-saved revision and fresh reviews. |
| Fresh comprehension review | Pass | Only supported limitation warnings; finite-input scope retained. |
| Fresh critic review | Pass | No fabricated blocking issue for the complete finite-input plan. |
| Review of conflicting units | Pass | Blocking issue cites the actual percent/fraction conflict and source fields. |
| Review of embedded instruction | Pass | Blocking issue cites the actual instruction; no instruction execution or marker in the answer. |

These counts describe this case set only. Cases share fixtures/models and were
exposed to the implementer; a pass-rate confidence interval or held-out accuracy
claim would be unjustified. The scope differs from v1–v3, so the counts are not a
controlled estimate of model improvement. Passing individual regression targets
does not meet the requirement that all sixteen full answers pass.

## Software verification and release status

Current checks pass: 121 backend cases, 111 agent cases, 180 frontend cases, 89
infrastructure cases, six claim-design database groups, eleven existing-idea
database groups, frontend lint/build, infrastructure TypeScript build, and nine
browser flow groups. Lint retains one preexisting internal-navigation warning.
The SQL test also rejects the actual failed v4 report; synthetic all-pass records
used to exercise local publication are explicitly software fixtures.

The browser campaign covers explicit start, one-time initial call, reload,
read-only/attributed policy, proposal adoption, retained failed review and retry,
fresh reviews, readiness, freeze, idempotent queueing, exports, desktop/mobile
light/dark layouts, and unauthenticated Next sign-in return paths. Inspected
390px dark and 1365px light screenshots fit the viewport. Authentication, provider
responses, Storage and cloud dispatch in this flow are synthetic; components,
API, agent parser and isolated PostgreSQL are real local implementations. It
queues one job and records no networking measurements.

An initial fixture emitted the now-forbidden metric criterion and correctly
failed. Its original failure and later correction remain retained. Earlier local
unit/build failures from policy-file placement, stale fixture expectations and
TypeScript scanning archived evidence were also corrected and recorded in the
[software verification history](claim-design-correction-validation/software-validation.json).
These are software/fixture failures, distinct from the seven actual-answer
quality failures. No provider candidate was retuned or rerun.

Publication requires the exact v4 candidate, frozen cases/policy, all sixteen
passing raw and rendered answer reviews, and declared evaluator/reviewer identity
and independence. This requirement is **not met**. No publication or production
deployment was performed. Conditional verification gaps remain legitimate Google
authentication, production boto3/persistence, remote Supabase Storage and actual
cloud networking execution. Local tests used Python 3.13; Lambda Python 3.12 was
not exercised. Existing historical paper assessments were not reassessed.

## Reproduction and resources

From `jumpserve-back-end`:

```sh
python3 -B -m unittest discover -s research_workflow/tests
```

From `jumpserve-infra`, with the documented isolated PostgreSQL cluster on port
54477 running:

```sh
python3 -B -m unittest discover -s test -p 'agent*_test.py'
python3 -B bin/prepare-research-runtime.py
python3 -B test/check_claim_design_database.py
python3 -B test/check_research_ideas_database.py
env JUMPSERVE_BACKEND_CHECKOUT=../jumpserve-back-end npm test -- --runInBand
npm run build
python3 -B test/serve_research_ideas_fixture.py --claim-design
```

From `jumpserve-front-end`, with the fixture on 4103 and the existing Next server
on 6001:

```sh
npm run lint
npm test
npm run build
node scripts/verify-claim-design.mjs
```

The actual billed command was
`python3 -B test/evaluate_claim_design_v2.py --live`; its exact evaluator, cases,
prompt, schema, parser, policy and compiler bytes are frozen under
`claim-design-correction-validation/evaluation-v4/inputs/`. The declared campaign
is exhausted; another live run is a separately declared follow-up, not the same
evaluation. Prefer inspecting the archived outputs to repeating billed calls.

AWS account 395567831870 and configured Supabase project regphejnlvfpyokpniny were
verified before calls. One sandbox STS preflight failed before any provider call;
the evaluator was rerun with network access. Sixteen serial Bedrock calls used
`us.anthropic.claude-sonnet-4-6`, us-east-1, temperature 0, without retries:
64,716 input tokens and 9,945 output tokens, over 131.642 seconds. Planning output
was bounded to 4,096 tokens, review output to 2,048; messages to 24 KB plus the
separately retained trusted prompt/schema. Measured charges, cost estimates,
local compute and storage allocation remain unknown, not zero. CLI JSON bytes
and canonical SDK messages are retained; original HTTP response bytes are not.

The [artifact manifest](claim-design-correction-validation/artifact-manifest.json)
records byte counts and SHA256 values verified after copying/retrieval. The
[targeted source inventory](claim-design-correction-validation/sources/inventory.json)
distinguishes retrieved bytes from partial substantive review. Statistical guard
rationale follows the [ASA's 2016 guidance](https://www.amstat.org/docs/default-source/amstat-documents/p-valuestatement.pdf)
and [NIST TN 2106, section 5](https://doi.org/10.6028/NIST.TN.2106); this assessment
does not claim full review of those sources' associated literature.
