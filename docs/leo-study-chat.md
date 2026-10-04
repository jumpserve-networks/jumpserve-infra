# LEO study data and AI chat

The `leo-emergency-failover` module explains recorded CosmoSim reproduction
results through the existing JumpServe agent. Results, methods, literature and
JSON downloads are public. Chat requires a verified Google Supabase session;
country links prepare an editable question and preserve it through login.

## Recorded state

The two study campaigns have been imported into JumpServe's Supabase project
`regphejnlvfpyokpniny`: 448 initial states/346 configurations and 114 exploratory
follow-up states/30 configurations. Scientific methods and remaining claim gaps
are documented in `jumpserve-back-end/experiments/leo_failover/README.md`.
The schema changes below and the evaluated prompt publication are applied.
The agent and frontend use the existing production deployment workflows; no
additional AWS application infrastructure is needed for the simulation.

The active LEO prompt is saved in the existing prompt tables:

| Field | Value |
| --- | --- |
| Prompt UUID | `ec00a4b6-718c-4e69-9c0f-283b9f251002` |
| Version | `leo-failover-results-v1` |
| Content SHA-256 | `13c3e9a8418ebf7f5e3faca69798d8a893cb7aa8b580dc72905aebf300acaf08` |
| Model | `us.anthropic.claude-sonnet-4-6` |
| AWS model Region | `us-east-1` |
| Analysis/capability version | `leo-failover-chat-v1` |
| Answer evaluation | All eight required cases passed |

The full passing report is in `agent_prompt_publications.evaluation_report` and
local ignored `.test-artifacts/leo-agent-evaluation.json`. It records exact
prompt identity, content hash, model settings, evidence hash, answers, tool
calls and grader judgments. Earlier failed evaluation attempts are retained
locally; unsupported explanations and missing-data substitution were corrected
in prompt/evidence instructions before publication. Model grading is a
regression check, not proof of scientific accuracy or comprehensive AI safety.
Emulated and real-world active prompt pointers were preserved.
The non-sensitive case outcomes and report hash are retained in
[`leo-agent-evaluation-summary.json`](leo-agent-evaluation-summary.json).

## Ownership and access

The backend validates `module_id`, owns prompt/tool selection and rejects a
session belonging to another module or user. `leo-emergency-failover` exposes
only `get_leo_study_results`, `get_leo_scenarios` and `get_leo_literature`.
These read bounded, explicitly projected public research relations; none can
launch, cancel or mutate experiments. Scenarios have explicit pagination and
complete matching fields. Missing records stay unavailable rather than zero.
Follow-up summaries are identified separately from the primary campaign.

The prompt distinguishes published capacities, corrected simulation results and
untested operational assumptions. It forbids confidence intervals from adjacent
deterministic seconds, invented discrepancy causes, using cable capacity as
observed traffic loss, or treating an allocation change as a controlled beam
effect. Bibliographic/source text is untrusted evidence, never instructions.
Answer provenance and saved conversations use the existing agent persistence
functions with the module and authenticated user attached.

The frontend queries conversations by both user and module and checks the
backend's advertised module capability before sending a question. An older
backend therefore cannot silently answer this module using emulated tools.
Public pages and downloads query with the ordinary Supabase client; no service
credential is bundled into browser code.

## Migration and eventual deployment order

For production releases:

1. Apply `database/202610040001_leo_study.sql` and
   `database/202610040002_leo_prompt_publication.sql`. They extend existing prompt
   and session module constraints and create six dedicated public result tables
   with RLS and browser write denial. The first migration explicitly removes the
   default anonymous-read restriction only from those six result tables.
2. Import both completed campaigns with `bin/leo-study-database.py`. Its seed
   insert never replaces an existing prompt, and its printed status reflects
   the actual active/published/draft state.
3. Publish the evaluated LEO prompt before enabling the agent/frontend.
   This prerequisite is already met in the current database. The publication
   function requires all eight exact case names, evaluated identity/hash/module,
   model/analysis metadata and the expected prior active pointer.
4. Deploy the module-aware agent using the repository's agent deployment
   workflow, then deploy the frontend with its existing Supabase and agent URL
   variables. No new public environment variable is required.
5. Verify public results/JSON and an authenticated chat end to end. Check
   deployed capabilities and returned module/prompt provenance. Preserve country
   deep links and confirm that prepared questions are not automatically sent.

A live browser chat through the deployed agent cannot be claimed verified until
that agent advertises the new capability and an authorized Google session is
available. The deployment workflow evaluates the active LEO prompt alongside
the emulated and real-world prompts before deploying the infrastructure.

## Evaluation and future prompt revisions

Published prompt versions are immutable. Create a new draft with the existing
`bin/agent-prompts.py` flow rather than editing the seed or active published row.
The manually triggered **Publish Agent Prompt** GitHub workflow now includes
`leo-emergency-failover`, evaluates the selected UUID with its own suite, and
uploads the LEO evaluation report. It uses the CI credential chain and checks
that the AWS account is `395567831870`.

For a local evaluation of a specific draft, from `jumpserve-infra`:

```bash
/Users/Shared/allstar/jumpserve-back-end/experiments/leo_failover/.venv/bin/python -B test/evaluate_leo_agent.py --live --profile jumpserve --prompt-id <draft-uuid>
```

Add `--publish --actor <name>` only when publication of that reviewed draft is
intended. `--profile jumpserve` selects the verified local account; when omitted,
the evaluator uses the normal AWS credential chain for CI. A failed suite never
publishes. The evaluator uses production read tools to capture evidence once,
then runs controlled missing-record and prompt-injection variants without test
launching or study writes. Bedrock evaluation makes billed model calls.

The eight cases cover unit conversion, numerical discrepancy, replication,
missing data, cable proxies, source/claim coverage, untrusted text and allocation
confounding. Ordinary verification requires no model calls:

```bash
npm run test:agent
PROMPT_TEST_DATABASE_URL=postgresql:///jumpserve_prompt_test npm run test:agent:database
```

The isolated Postgres checks roll back all fixtures. They cover public research
reads, browser write denial, private prompts, publication rejection/activation,
session ownership and cross-module history. Frontend `npm test`, lint and build
cover parsing, configuration matching, capability checks and route integration.
