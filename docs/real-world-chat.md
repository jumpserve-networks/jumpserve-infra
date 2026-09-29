# Real-world measurement chat

The authenticated agent accepts `module_id` as either
`congestion-control-emulated` (the legacy default) or
`congestion-control-real-world`. The server maps it to a fixed tool allowlist and
an independently published database prompt. It never accepts system instructions,
a prompt UUID, or arbitrary tool selection from the browser. An authenticated
`action: capabilities` probe lets the frontend detect an older agent before
sending the user's actual real-world question.

The real-world agent has four read-only tools:

- `search_real_world_tests`: newest-first public records, bounded pagination and
  explicit exact CCA/status filters. It does not claim complete history from one page.
- `get_real_world_results`: saved normalized results, current status, warnings,
  comparison eligibility, placements, sample counts, and software/source provenance.
  Missing reports remain unavailable; saved/current record mismatches are marked stale.
- `get_real_world_trace`: unsampled pages of throughput, TCP, or queue traces,
  retaining zero/null values, clock definitions and pagination coverage.
- `compare_real_world_tests`: 2–20 explicitly selected UUIDs, independent whole-test
  bootstrap intervals and the same matching rules/units as the reporting workspace.
  Unmatched blocks, exclusions, duplicate IDs, and insufficient repetitions stay visible.

Tools read only `real_world_runs` and `real_world_reports`; they do not read private
job records, private artifacts, requester identities, or other users' conversations.
Receiver traces are not fed into prompts wholesale. Hypothesis notes remain
untrusted evidence. Launch and cancellation tools are unavailable in this module.

`database/seed-real-world-agent-prompt.json` is the initial draft, not a runtime
fallback. Its system prompt and research context define duration-based receiver
throughput, milliseconds for sender RTT, estimated BFIFO drain time, diagnostic
preflight ping, independent clocks, complete-set fairness, software-version
limits, and matched comparisons. These rules explicitly prevent importing
emulated delay parameters, FCT workloads, or unsupported BBR-version claims.

## Release order (only when deployment is authorized)

1. Run `python3 -B bin/agent-prompts.py migrate` against the verified JumpServe
   project. It applies `202609290001_real_world_agent.sql` once, backfills existing
   prompts/sessions to the emulated module, preserves the current emulated active
   version, and inserts the real-world seed as an unpublished draft.
2. Evaluate and publish the real-world draft with the existing workflow or:

   ```sh
   python3 -B test/evaluate_agent.py --live --module congestion-control-real-world \
     --bootstrap-if-empty --actor <operator> \
     --output .test-artifacts/real-world-agent-evaluation.json
   ```

   This makes billed Bedrock calls using synthetic, fixture-only tools. It does
   not launch EC2 tests. All eight cases must pass. SQL verifies the module,
   content hash, exact case set, and unchanged active pointer before publication.
   Re-running bootstrap evaluates the existing active version without replacing it.
3. Deploy the agent code, then the frontend. The deployment workflow evaluates
   both modules before deploying. A missing/unpublished prompt fails closed with
   HTTP 503. No frontend or Python prompt fallback supplies emulated instructions.
4. Verify signed-in result-to-chat navigation, the selected module's saved history,
   and a real result lookup. Prompt-only revisions thereafter use the publication
   workflow without an application deployment.

The new SQL retains backwards-compatible default RPC arguments for existing
emulated callers. `agent_prompt_versions.module_id` and session module identity
are immutable. The active pointers are independent, and the atomic save function
checks both user ownership and module before updating a conversation. Answers
retain their exact published prompt ID, model ID and analysis version.

## Local checks

```sh
npm run test:agent
PROMPT_TEST_DATABASE_URL=postgresql:///jumpserve_prompt_test npm run test:agent:database
```

The database check refuses any database not named `jumpserve_prompt_test` and
rolls back all fixture/schema changes. It tests legacy compatibility, independent
publication, wrong-module evaluation rejection, prompt immutability, transactional
session isolation, and denied anonymous/browser RPC access. Python tests cover
report semantics, missing/stale data, bounded trace reads, comparisons, and
handler authentication/tool selection. Live answer evaluations are a separate
release gate and are not implied by passing local deterministic tests.
