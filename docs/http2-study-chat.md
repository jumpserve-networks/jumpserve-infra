# HTTP/2 compliance study: evidence, chat and release

The public module is `/module/http2-compliance-study`. It compares published
paper values with a frozen reanalysis of archived author measurements and a
separately declared, owned-loopback endpoint follow-up. No simulator or orbital
model is involved. Scientific reproduction remains partial even when the
software feature is released.

Scientific inputs, six protocols and locks, original artifact revisions,
reproduction commands, source inventory and limitations are in
`jumpserve-back-end/experiments/http2_compliance/README.md`. Original downloaded
bytes and author checkouts are retained locally; original author payloads are
also retained in backend-only Supabase artifact records. Public JSON contains
7,176 archived case observations and 84 separately identified loopback frames;
CSV exports the archived observations with missing fields blank.

## Claim coverage

| Claim / location | Assessment | Evidence and practical limit |
| --- | --- | --- |
| 156-case universe; Tables 8–9, Appendix B | Reproduced | 78 client, 78 server and 61 explicit mirrored pairs; excluded RFC requirements remain excluded. |
| Table 5 counts | Reproduced | All 15 rows exact under the released author classifier: 1,745 rejected, 205 accepted, 856 drops, 1,950 total. Rejection is not compliance. |
| Figure 4 vectors | Inconclusive | Archived vectors retained; individual PDF raster cells are not all independently checked. |
| Figure 5 side ratios | Reproduced | Ten configurations, 78-case denominators, ±0.05 percentage points for rounding; broad-rule scores do not validate every RFC response. |
| Figure 6 mirrored differences | Reproduced | Ten configurations using 61 declared pairs, same rounding criterion; descriptive behavior only. |
| Figure 7 historical changes | Discrepant | Nine checked deltas agree; raw Traefik drops +90 versus published/stored +12. Cause unresolved. |
| Figure 8 translation deltas | Discrepant | Released category-mapping bug diagnosed with a separate control. Corrected matched accepted deltas +6/−1/+1/+1 versus +8/+5/+5/+2. Camera-ready generating code remains unknown. |
| TLS equivalence | Inconclusive | Historical labels/configurations do not establish matched equivalence or a causal TLS effect. |
| None fully compliant | Inconclusive | This assessment does not independently validate all case-level response semantics. A verified finite counterexample could establish noncompliance. |
| HTTP/2 stricter than prior HTTP/1.1 | Inconclusive | Different case universes and versions; 1,745/1,950 versus 128/564 is not a matched causal comparison. |
| Frame header, §2.1 | Discrepant | RFC 9113 and Table 1 specify 9 octets = 72 bits, versus prose 12 bytes; expository error alone does not invalidate the campaign. |
| Local/cloud fleet | Untested | Archived data reanalysis and current Node loopback controls are not independent historical proxy/cloud replication. |
| TCP transparency check | Inconclusive | Matching sequence numbers exclude some splitters, not every intermediary. |
| Normative suite improves security | Untested | No intervention, exploit validation or measured interoperability benefit. |

The archive retains 443 unknown outcomes, including 129 in the primary subset.
The main loopback follow-up records 72 outcomes: 42 planned-code agreements and
30 mismatches, with all positive controls passing. It uses Node 24.4.1 on one
macOS arm64 workstation, without TLS. Five malformed cases return code 2 instead
of planned code 1; these are planned-code mismatches, not independently confirmed
RFC bugs. Same-host repeats and designed cases do not support a population CI
under this protocol. Observation durations are not network RTTs.

The inventory has 49 entries: main paper plus 48 direct citations; 3 complete,
29 partial, 8 unreviewed and 9 unavailable. All 40 adopted original hashes pass
independent retained-file checks. Hash verification does not upgrade review
status. Complete supporting-literature coverage is not claimed.

## Database and chat ownership

Target AWS account: `395567831870` using the `jumpserve` profile. Target Supabase:
`regphejnlvfpyokpniny`. Purpose-specific import/deployment tools verify those
targets before mutation. Connected tools for other Supabase projects are not
used. Migrations `202610040003` through `202610040009` create eleven study
relations, extend module/prompt constraints, preserve unsigned 32-bit error
codes, enforce manual answer review and save model usage and typed evidence
selection with answer provenance.

Ten study relations are public SELECT-only with RLS; author raw/evaluation
artifacts are backend-only. Browser writes are denied. Original execution dates
and resource counts remain null where unavailable. Campaign, configuration,
run, measurement, source and claim records remain relational, with explicit
failed statuses and reasons. Published counts are separate columns.

Chat reuses `ChatPanel`, Google authentication and the existing prompt/session
architecture. Backend module selection owns prompt and tool selection; it checks
session user and module before invoking a model. Only three bounded read tools
are available: `get_http2_study_results`, `get_http2_configuration` and
`get_http2_literature`. Every turn attaches a fresh results snapshot as a
recorded tool result. Configuration/source strings are untrusted evidence.
Links prepare editable questions without sending them automatically.

The model selects validated topics, configuration IDs and optional source/case
IDs. A versioned backend renderer derives numerical claims from the current
read-only snapshot and displays recorded assessments and their limitations.
Incidental model prose is neither displayed nor used as a scientific conclusion.
The typed selection is retained with the saved answer. This intentionally limits
the chat to recorded evidence; it does not provide arbitrary new scientific
inference. Failed rendering preserves a failed, owner-scoped generation and its
available token costs. The evaluation uses this same renderer and schema.

The historical report key `human_review` records secondary answer inspection by
Codex, with `reviewer_type` explicitly identifying an AI agent. It is **not** a
human scientific review or user approval. Failed automated judgments remain
unchanged in retained reports. The public prompt/answer download is exported
from the active, evaluated database publication only after these checks pass.

HTTP/2 uses `us.anthropic.claude-sonnet-4-6`, temperature 0, analysis
`http2-assessment-v3`; existing modules keep their model selection. Saved answers
and responses include prompt UUID/version/content hash, analysis version, model
usage and an estimated list-price cost. Authenticated Google owners can retrieve
their answer provenance; other users and cross-module requests are denied.

Earlier free-form Sonnet/Opus rounds are preserved as separate evaluations.
The final typed-selection campaign uses Sonnet after Opus reached its daily
token quota. Selection metadata avoids resending complete numeric vectors;
the full fresh snapshot remains available to backend rendering and read tools.

## Evaluation and release order

1. Apply/import with `python3 -B bin/http2-study-database.py --apply` for a new,
   verified study bundle. Do not overwrite an existing campaign with a different
   protocol or analysis. `--prepare` applies subsequent migrations and inserts
   immutable draft seeds; `--verify` reads persisted counts.
2. Run `npm run test:agent`, `npm run build`, `npm test`, and isolated database
   checks with `PROMPT_TEST_DATABASE_URL=postgresql:///jumpserve_prompt_test
   npm run test:agent:database`. Frontend requires its tests, lint, production
   build, `npm run verify:http2` and browser checks of completed data.
3. Evaluate with the dependency-pinned backend LEO virtualenv:
   `../jumpserve-back-end/experiments/leo_failover/.venv/bin/python -B
   test/evaluate_http2_agent.py --live --profile jumpserve`. This makes billed
   Bedrock calls; no experiment launch or study mutation occurs. Each UUID report
   captures answers, actual tool calls, prompt/evidence/code hashes, judgments,
   timestamps and tokens. Eight fixed cases cover units, missing data, literature
   coverage, uncertainty, discrepancies, injected source instructions, rejection
   interpretation and error scope. They are regression checks, not a reliability
   sample. Failed and later rounds remain separate.
4. Review all actual answers against evidence, including claims the automated
   grader missed. Save `human_review` with reviewer, time, all eight case names,
   findings and a true/false decision. Only passing automatic and manual reviews
   can publish via `--publish-reviewed <evaluation-uuid> --profile jumpserve`.
   An earlier automatically passing v3 was disabled after manual review found
   a false claim, before this module's backend deployment. Published records are
   retained immutably. `--save-evaluations` persists all UUID reports privately
   and aggregates their per-model token/cost estimates publicly.
5. Restore the existing dependency layer with `bin/prepare-agent-layer.py`.
   `python3 -B bin/deploy-http2-agent.py --diff` checks the existing Agent stack.
   `--deploy` refuses absent manual approval or changed evaluated tool/context
   hashes and deploys only `JumpServeAgentStack`. It does not deploy unrelated
   stacks. Push the frontend's reviewed commit to main for its existing Amplify
   build only after migration, publication and backend release pass.
6. Verify deployed code and anonymous denial using
   `../jumpserve-back-end/experiments/leo_failover/.venv/bin/python -B
   bin/verify-http2-agent.py`; run frontend `npm run verify:http2 --
   https://jumpserve.quaint-lab.org` and desktop/mobile browser checks. Exercise
   an authenticated chat only with an available legitimate Google session.

Live production status, exact released prompt/evaluation identity, verification
evidence and remaining gaps are recorded in `http2-release-report.json`. Cost
estimates include failed rounds and use the recorded per-model prices. They are
not reconciled billing; existing hosting/build charges, workstation allocation
and Codex orchestration charges are unavailable. No AWS experiment instances
were provisioned.
