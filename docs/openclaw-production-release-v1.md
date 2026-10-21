# OpenClaw subscription release

The application candidate uses a dedicated AWS OpenClaw worker for autonomous
paper assessment. Defaults remain $100 in aggregate paper commitments and seven
elapsed days, with no AI turn-count ceiling. Every turn retains its prompt,
version, original response, available usage and outcome. Missing inputs and
uncertain calls can still prevent a scientific conclusion.

The worker pins OpenClaw 2026.10.5, Node 24.16.0 and `gpt-6.1-sol`. Native
host-specific Sign in with ChatGPT authorizes subscription use; API-key and
Bedrock fallback are disabled for this assessment configuration. Other existing
AI modules retain their own separately published configurations.

The private worker has encrypted storage, no inbound security-group rules and
SSM administration. A callback-only correction preserves the original native
module before changing `localhost` to `127.0.0.1`. Native PKCE, state, signature
verification and credential refresh are retained. OAuth grants and host auth
databases never enter Git, browser responses or the per-turn process.

SQL binds each exact reserved turn to one fenced dispatch. A fresh OpenClaw
workspace has no tools, plugins or inherited cloud/provider credentials. Its
loopback bridge permits one actual provider inference. A lost or expired lease
becomes unknown and requires reconciliation; it does not trigger a second call.
Reviewed networking adapters execute experiments and persist measurements.

Candidate v9's twelve automatic checks passed but substantive AI inspection
found phase-inapplicable evidence references in four answers. That candidate is
rejected and retained. Candidate v10 narrows and validates the phase contract.
All sixteen actual answers passed the declared checks and substantive review:
twelve reused development regressions and four newly reserved first-use checks.
The implementer, evaluator and reviewer are AI and nonindependent. This is not
human review, independent validation, or a new scientific result.

The original IPv6 subscription pilot remains unchanged: six archived checks
recorded agreement for 1,152 cells, but its controller stopped at the historical
25-attempt ceiling before final assessment. Its inconclusive label, failures,
cost commitments and original protocols are preserved. The new application
policy does not reset that campaign's resources or rewrite its findings.

## Reproduction and release order

1. Verify AWS account `395567831870` and Supabase project
   `regphejnlvfpyokpniny` using `bin/openclaw-release.py inspect`.
2. Run backend/frontend tests and builds, infrastructure tests with the explicit
   backend checkout, actual SQL autonomy/turn-policy/PDF/dispatch checks and the
   existing desktop/mobile browser campaign. Exact report hashes are in
   `openclaw-production-validation-v1.json`. All commands are existing scoped
   repository entrypoints; the browser campaign explicitly uses fixture auth,
   provider responses and Storage.
3. Pin the clean backend commit in `research-workflow-runtime.json`, then run
   `bin/prepare-research-runtime.py` and `bin/prepare-openclaw-worker.py`.
4. Diff/deploy the separate `JumpServeOpenClawStack`. Complete native ChatGPT
   consent on that host through an SSM loopback tunnel. Never copy a developer's
   grant. Verify native refresh, the model catalog and actual inference.
5. Hold admission and drain active leases. Apply context recovery, unlimited-turn
   policy, private dispatch, retained v9/v10 candidates and the new publication
   guard with `bin/openclaw-release.py migrate`. The old local pilot audit
   migrations 003–007 are preserved source and are not required in production.
6. `bin/archive-openclaw-evidence.py` uploads the exact grant-free original model
   requests, SSE, native outputs and source snapshots to private Storage and
   verifies every retrieved hash. Transient state and auth files are explicitly
   excluded. Publish v10 through `bin/openclaw-release.py publish`; retain failed
   v9 and passing v10 in the private immutable evaluation relation. Existing
   module prompt pointers remain unchanged.
7. Review the scoped benchmark diff. Deploy while admission is held, verify the
   exact Lambda sources and private database/security configuration, then
   activate the evaluated worker. Existing benchmark parameters must match.
8. Push the frontend `main` revision and verify its Amplify deployment. Exercise
   desktop/mobile themes, public pages, missing/invalid states, navigation and
   sign-in return paths. Use a legitimate Google session for an actual persisted
   autonomous request and bounded experiment. Mark synthetic controls separately
   from archived paper checks and new empirical measurements.
9. Preserve final deployment receipts and unresolved conditional gaps in a new
   release status record. Local success is not production verification.

The first host bootstrap failed because `awscli2` is not the Amazon Linux package
name. Its original user-data/logs remain retained. A separately recorded recovery
changes only that package token to `awscli-2`; source refresh preserves the old
runtime directory and the separate native authorization directory. The versioned
protocol amendments document this infrastructure failure and correction.

The passing candidate made sixteen real subscription requests; the rejected
candidate made twelve. Their aggregate $28 orchestration reserve is not an
inference bill. Actual subscription allocation and infrastructure/storage charges
are unknown, not zero. Ongoing host compute/storage is unallocated. Quota pauses
must not enable paid fallback.

At this record's creation, local checks pass and the private host is installed.
Renewed AWS access, native host authorization, production schema/prompt activation,
controller/frontend rollout and deployed authenticated checks remain pending.
See subsequent release status records for the actual deployed state.
