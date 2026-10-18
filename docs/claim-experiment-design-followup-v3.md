# Claim designer: seven-regression follow-up

Implemented locally, 2026-10-18 UTC. The seven original regression cases pass in
the revised clarification-first flow. **All twenty retained-answer checks pass
after a unit-validator correction and offline replay.** The original final live
pipeline result remains recorded as 19/20; it has not been rewritten as a clean
live run. No production prompt publication, deployment or scientific claim
reassessment was performed.

| Evidence | Result | Meaning |
| --- | --- | --- |
| Previous v4 assessment | 9/16 | Original failures retained unchanged. |
| Candidate v5, actual provider answers | 16/20 | Remaining failures included an echoed injection marker, an unsupported quantity label, delay arithmetic ambiguity and a dropped observation count. |
| Candidate v6, original live pipeline | 19/20 | All provider responses returned; literal quote/unit validation rejected a correct equivalent quantity. |
| Corrected v6 parser, unchanged-answer replay | 20/20 | Exact original model requests/responses verified; corrected deterministic processing and complete answer review, with no new provider call. |

The case sets and output contracts differ across versions, so these counts are
not a controlled estimate of model improvement. Cases are exposed/tuned
development checks, not independent held-out validation. Evaluator and reviewer
are the primary Codex AI implementer, not human or independent reviewers. No
pass-rate confidence interval is justified.

The [frozen protocol](claim-experiment-design-protocol-v3.md),
[v6 amendment](claim-experiment-design-v3-amendment-v6.md) and
[parser follow-up](claim-experiment-design-v3-parser-followup.md) preserve the
sequence of declared methods. Original provider reports, failures, raw bytes and
reviews remain separate under [the evidence directory](claim-design-followup-validation/).
The [reviewed replay report](claim-design-followup-validation/v6-replay-exact-final/evaluation-reviewed.json)
contains each case's judgment and remaining wording/usability warnings.

## Implemented controls

Incomplete information now yields tailored questions and no proposal. Such an
answer cannot be adopted or create a new plan packet. A complete saved descriptive
pilot is referenced rather than reconstructed. A new candidate requires a non-null
protocol, resolved questions, original claim/source identity, protected configuration
and resource fields, and retained per-metric observation counts. Fresh reviews,
owner acceptance, freezing and queueing remain separate gates. Earlier incompatible
proposals remain visible but cannot bypass the corrected adoption contract.

The server supplies a versioned runner/metric context: flow completion time is
recorded in ms and differs from RTT/delay placement; a scalar delay does not choose
a direction; transport emulation does not supply an optical/atmospheric/orbital
availability model. These checks address the seven earlier failure cases:

| Earlier case | Tested resulting behavior |
| --- | --- |
| Networking draft | Asks for actual placement/workload/resources instead of adopting one-way delay as a fact. |
| Missing optical equipment | Asks for a definition and applicable model/data/hardware, without substituting netem for physical availability. |
| Causal/generalization challenge | Uses scoped guidance and asks about actual delay placement, avoiding one-way/round-trip flow-completion terminology. |
| Seconds/milliseconds ambiguity | Keeps quantity identity unresolved and computes owner-supplied unit values independently before any threshold choice. |
| Embedded instruction | Ignores the instruction without quoting its marker in the answer; no execution/publication. |
| Correlated snapshots | Prevents automatic independent-sample conclusions; asks about sampling and run-level dependence. |
| Equivalence challenge | Requires a justified margin and reviewed design, while leaving placement unresolved. |

Mode/status text and methodological guidance are explicitly attributed JumpServe
templates. The model chooses guidance topics and writes questions/candidate content;
those selections remain model judgments. Raw answers are retained before parsing.
This is an explicit response contract, not hidden editing of a bad answer. The
interface distinguishes questions from candidates, shows conversion provenance,
and keeps the descriptive decision policy read-only.

The exact-equivalence correction addresses a demonstrated software mechanism:
the model selected **200 ms** with exact owner quote **0.2 seconds**. The first
validator required matching spellings, although the quantities are equal. The
corrected validator separately parses the one unambiguous quoted quantity and
checks equality using exact Decimal coefficient/exponent shifts, preserving both literal source
and selected representation. Independent Fraction checks confirm the arithmetic;
1000-fold errors, context-rounding differences, truncated/signed/compound-unit quotations, booleans, nonfinite values and bounds
violations still fail. Recorded zero remains valid. No tolerance or scientific
threshold is introduced, and source quotation does not verify the paper's value.

The replay regenerates and byte-compares every system/messages/channel input,
verifies original provider/message hashes, and checks both complete/new candidates
with the real compiler and exact configuration/resource/coverage matches. Prompt,
schema, runner context, requests and raw model answers are unchanged. Only
deterministic output validation changed; no third model candidate was evaluated.
The original failed live report is preserved alongside the corrected replay.

## Verification, publication and limits

Current checks pass: 122 backend tests, 116 agent tests, 180 frontend tests, 89
infrastructure tests, six claim-design SQL groups, eleven existing-idea SQL groups,
ten browser groups, frontend lint/build and infrastructure TypeScript build. Lint
retains the preexisting `auth-button.tsx` navigation warning. SQL verifies exact
replay lineage, rejects failed reports and altered provider/parent hashes, and
uses the actual reviewed replay report for positive publication testing in an
isolated local database. This does not publish the production prompt.

The browser fixture exercises clarification without packet mutation, denied
clarification adoption, exact unit equivalence through the real agent/API/Postgres
path, candidate adoption, retained failed review and retry, fresh reviews/readiness,
freeze, idempotent queueing, downloads, 1365/390px light/dark layouts and actual
Next unauthenticated sign-in return paths. Desktop/mobile screenshots were inspected;
conversion values/provenance were also checked in the DOM and database. Fixture
authentication, provider responses, Storage and cloud dispatch are synthetic.
No networking job was actually executed and no measurements were created.

An additive publication guard binds the exact corrected parser/agent, unchanged
schema/context, parent live report, request/provider manifests and all twenty
raw/rendered output hashes. It distinguishes `archived-model-output-replay` from
`actual-model-development`; failed reports cannot be relabeled into a publication.
All proposed plans still require user adoption and fresh reviews. Production
release remains unperformed; legitimate Google authentication, production boto3
and persistence, remote Storage, Lambda Python 3.12 and actual cloud execution
remain conditional verification gaps. Local Python checks used 3.13.

The designer remains limited to descriptive pilots; it does not implement a general
inferential statistics engine or validate arbitrary paper claims. No empirical
study, causal claim or physical effectiveness result follows from these software
checks. Some questions retain wording or runner-choice caveats: symmetric
per-direction examples do not resolve asymmetric layouts; duration-based workload
examples need a suitable executor; separately initiated runs are not automatically
independent. These are prospective clarification alternatives, not adopted or
executable configurations. Their caveats are retained in case judgments. Full
answer review means examining returned fields and rendered guidance against these
fixtures, not complete literature review or universal scientific validation.

## Reproduction and resource record

From `jumpserve-infra`, offline reanalysis uses:

```sh
python3 -B test/evaluate_claim_design_v2.py --replay-v6 --campaign v3 --candidate v6
```

The live campaign's two-candidate/forty-call budget is exhausted. Do not repeat
the billed flags as if they were the same evaluation; archived original inputs
and provider bytes support reproduction of the deterministic analysis. Temperature
zero does not guarantee future identical provider output, and model weights were
not archived.

Local commands remain:

```sh
# jumpserve-back-end
python3 -B -m unittest discover -s research_workflow/tests
# jumpserve-infra; isolated PostgreSQL port 54477 for database/browser fixtures
python3 -B -m unittest discover -s test -p 'agent*_test.py'
python3 -B bin/prepare-research-runtime.py
python3 -B test/check_claim_design_database.py
python3 -B test/check_research_ideas_database.py
env JUMPSERVE_BACKEND_CHECKOUT=../jumpserve-back-end npm test -- --runInBand
npm run build
python3 -B test/serve_research_ideas_fixture.py --claim-design
# jumpserve-front-end; fixture 4103 and Next 6001
npm run lint
npm test
npm run build
node scripts/verify-claim-design.mjs
```

Forty serial actual Bedrock calls used `us.anthropic.claude-sonnet-4-6`, us-east-1,
API endpoint region us-east-1 (actual provider compute location was not exposed), temperature 0, planning output <=4096 tokens, review output <=2048, bounded 24 KB
messages plus retained trusted prompt/schema, and no automatic retries. AWS account
395567831870 and configured Supabase project regphejnlvfpyokpniny were verified
before calls. Recorded usage totals **201,140 input tokens and 12,254 output
tokens**; provider campaigns lasted 162.667 seconds combined. The replay made zero
provider calls and does not count those tokens again. Measured charges, estimates,
local compute, authoring/reviewer model usage and shared storage allocation remain unknown, not zero. Original CLI
JSON bytes are retained; original HTTP response bytes are unavailable.

The [artifact manifest](claim-design-followup-validation/artifact-manifest.json)
records sizes/hashes verified after copying, and the software report identifies
each check and its limits. Earlier 268-artifact and 166-artifact inventories were
verified unchanged. Hash verification establishes integrity, not substantive review
or independent scientific validity.
