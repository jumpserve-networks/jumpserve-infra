# Research workflow: architecture, verification and release

The subsequent [claim queue implementation](research-queue.md) adds dependency-aware
campaign scheduling and bounded workers, private operational tables and per-claim
progress. Its [protocol](research-queue-protocol-v1.md) and
[validator correction](research-queue-amendment-v2.md) preserve earlier reports.
The original validation report below describes the original implementation bytes;
it is not verification of the later queue release. The current runtime manifest
contains six files; the original four-file manifest is archived separately.

Implementation of `pdfs/research-claim-verification-workflow.pdf`. The declared
scope is [implementation protocol v1](research-workflow-implementation-v1.md), with
preserved [v2](research-workflow-amendment-v2.md) and
[v3](research-workflow-amendment-v3.md) amendments. Backend usage and scientific
boundaries are in `jumpserve-back-end/research_workflow/README.md`.

## Implemented feature

- Public module: `/module/research-verification`; reviewed assessments, methods,
  source review coverage, configuration comparisons, descriptive plots, claim
  histories, prioritized evidence gaps and complete JSON/measurement CSV exports.
- Google-protected intake and owner workspaces. Existing login return paths retain
  the study and selected view. Owner writes use verified Supabase Google identity
  and backend ownership. A caller-supplied actor is never browser authorization.
- Eighteen relational tables in `202610070001_research_workflow.sql`, RLS enabled,
  browser writes denied. Owners, artifact metadata and audit actors are private.
  Originals live in the private `research-workflow-raw` Storage bucket.
- Immutable evidence, frozen protocols and amendments, campaign classes, failed
  and partial runs, separate published values, explicit non-recorded states,
  summaries, claim checks/assessments/gaps, reviewer provenance and publications.
- Publication captures a fixed record manifest and requires passed scientific
  scope and software reviews of that exact evidence. Later drafts stay private.
  Changes invalidate older reviews. Unresolved claims require current gap records.
- Bounded stdlib Python API and CLI; one registered deterministic numerical
  adapter and a documented external-campaign importer. No submitted-code execution,
  EC2 launch permission or model permissions in this runtime.
- The IPv6 bridge preserves its original 74-source/15-claim register and creates
  nine unresolved-claim gap records. Its original measurements, limitations and
  evaluated chat remain in the IPv6 DNS Study. This is not new scientific evidence.

Reviewers provide declared judgments; the publication function does not invent
human or independent review. Generic AI interpretation is disabled until a new
module prompt, bounded read tools, actual-answer evaluation and publication history
are implemented and evaluated. Existing study chats keep their own module scopes.

## Local release checks and precise limits

Run the backend development regressions, frontend tests/lint/build, CDK assertions,
isolated Postgres security/publication tests and the complete public browser story.
The implementation reviewer is the primary Codex assistant: **AI, implementer,
not independent**. Reused/tuned cases are development checks, not held-out science.

```sh
# jumpserve-back-end
python3 -B -m unittest discover -s research_workflow/tests -v
# jumpserve-infra (prepare from matching backend bytes first)
python3 -B bin/prepare-research-runtime.py
npm run build
npm test -- --runInBand
RESEARCH_TEST_DATABASE_URL=postgresql://michael@localhost:54477/jumpserve_research_workflow_test npm run test:research:database
# jumpserve-front-end
npm ci
npm test
npm run lint
npm run build
```

The transactional database test refuses non-isolated database names, imports the
exact local IPv6 register and rolls back all changes. PostgreSQL 17 tools used by
the fixture are under `/opt/homebrew/opt/postgresql@17/bin`. Use a dedicated local
cluster; do not substitute a remote Supabase connection. These tests model the
default restrictive anonymous policy and permissive unrelated Storage policies.

For browser checks, create the separate local `jumpserve_research_browser_test`
database, start `npm run test:research:browser-fixture` in infrastructure, and use
these commands in the frontend (separate terminals):

```sh
NEXT_PUBLIC_RESEARCH_WORKFLOW_API_URL=http://127.0.0.1:4102 npm run build
NEXT_PUBLIC_RESEARCH_WORKFLOW_API_URL=http://127.0.0.1:4102 npm start -- --port 3004
npm run verify:research
```

Playwright 1.62.1 is a pinned test dependency. On macOS the verifier uses installed
Google Chrome; otherwise install Playwright Chromium with `npx playwright install
chromium`. The verifier binds to the declared local origin and saves timestamped
reports/screenshots/exports under `.test-artifacts/research-workflow/`, preserving
failures. It waits for UI readiness and settled menus/themes, not background network
idleness. Do not deploy a build containing the local fixture API origin.

The browser fixture uses the **actual public API handler and snapshot code**, with
only the persistence HTTP transport replaced by isolated Postgres queries under
role `anon`. It also injects clearly identified invalid/unavailable transport cases.
The IPv6 register is real archived evidence; the numerical cells and publication
reviews are synthetic software fixtures. They do not establish new science,
independent review, live Supabase Storage behavior or a Google-authenticated request.

Local blockers: backend matching/missingness/budgets/ownership; database RLS,
private originals, immutable evidence/publication snapshots/review gates; frontend
tests/lint/build/plots/exports/navigation/desktop/mobile/themes/missing states;
runtime byte identity and bounded IAM. Conditional release checks require a live
Google session, remote Storage round trips and deployed end-to-end verification.
Actual owner browser execution and authenticated chat are not established by mocks.
No new generic chat candidate is published by this change.

## Production release order — explicit new deployment request required

This implementation turn does not deploy. The frontend repository's deployment
rule requires a new explicit request for these changes; earlier study deployment
authorization is not standing authorization for this new module.

1. Rerun local blockers on the exact release revisions, record any conditional gaps
   and require honest scope review. Keep authors' bytes/revisions and corrections
   separate. Commit/tag release revisions when authorized; the current runtime
   manifest labels working-tree byte hashes rather than claiming a new git commit.
2. Verify AWS profile `jumpserve` is account **395567831870** and the configured
   Supabase project is **regphejnlvfpyokpniny**. Before changes, use the guarded
   migration command. It checks STS and the exact Supabase Management API target:

   ```sh
   python3 -B bin/research-workflow-database.py --apply \
     --output .test-artifacts/research-workflow/database-apply-v1.json
   ```

   The command refuses an existing schema. Preserve migration bytes and this
   receipt. Future changes use new versioned migrations, never reset evidence.
   Without `--apply`, the command only verifies catalog/grants/Storage policy; it
   does not recover the originally executed SQL bytes.
3. Prepare `research-workflow-runtime.json` from the exact backend code and stage
   it with `bin/prepare-research-runtime.py`. The CDK construct rejects changed or
   absent runtime files, wrong AWS account and wrong Supabase project. Deploy the
   **JumpServeBenchmarkStack** with `-c researchWorkflowEnabled=true`, following the
   repository's existing CDK deployment entry point and review process. The context
   flag defaults off; ordinary unrelated stack operations do not add this feature.
4. Verify `/research/capabilities`, public empty/unavailable states and anonymous
   write denial. Exercise real private Storage upload/retrieval hashes and a genuine
   Google owner flow, including campaign failure/retry and cross-owner denial.
   Runtime: Python 3.12, 512 MB configured memory, 29 seconds, concurrency four;
   only the existing Supabase service-key secret is granted. No model/tool prompt
   changes are part of this runtime deployment.
5. Set `NEXT_PUBLIC_RESEARCH_WORKFLOW_API_URL` to the **API origin**, without
   `/research` (or retain the benchmark-origin fallback), before the frontend
   production build. Release the frontend only after the schema/API exist. Keep
   Supabase keys server-only; never expose a service credential to Next.js clients.
6. Use a trusted server operator to import the original IPv6 register with
   `import-ipv6 --persist --actor-id OWNER_UUID ...`. It creates a private draft,
   not a publication. Perform and record actual reviews, then publish through the
   owner API/UI. Never promote synthetic browser fixture reviews to production.
7. Verify deployed pages, complete exports, desktop/mobile/themes, provider sign-in
   return paths and real owner requests; retain usage, evidence and release status.

Rollback: disable/hide the new module/API through an authorized release, or append
a withdrawal publication with reason and the required passed review references.
Retain evidence and prior publication history; do not drop tables or overwrite raw
bytes. Withdrawal is currently available through the owner API, not a separate UI.

## Usage and evidence

Run usage contains input bytes, adapter wall time and missing charges/model usage
as null; artifact records contain original byte counts and verified retrieval time.
No experiment machines or evaluation calls are launched by this feature. Local
Codex/model charges and hosting/storage charges are not reconciled or assumed zero.
The validation report records measured values, estimates and unavailable usage
separately. Scientific coverage and software readiness remain separate judgments.
