# Source-bound experiment design

Implemented locally on 2026-10-17. **AI prompt publication is blocked; this is not
deployed or ready for production activation.** See the detailed validation report
in `jumpserve-infra/docs/claim-experiment-design-validation.md`.

Every recorded paper claim has a **Design an experiment for this claim** link.
For a current gap with no retained plan, **Run experiment now** opens the same
designer instead of ending at the unsupported-plan message. Existing retained
plan execution is preserved.

The designer creates or resumes an owner-private paper workspace, retaining the
exact claim/source/gap context. A recent explicit click can start its first AI
proposal; navigation, prefetch and reload alone cannot invoke AI. It asks tailored
questions, offers a complete proposed plan, and saves owner adoption as a new
version. Original scientific assessments are unchanged.

The steps are proposal, saved plan, fresh comprehension/critic reviews, accepted
readiness, frozen protocol, and queued experiment. Current-packet and protocol
gates are enforced in the backend and SQL. Supported networking specifications
use the existing automatic runners. Other domain work remains an explicit
operator task; a plan is not a measurement or claim finding. Known source bytes
must be identified before automatic execution. Source retrieval, full-text review
and claim extraction are separate work; the planner reads recorded metadata.

Routes:

- `/research-verification/design-claim/<studyId>/<claimId>` selects any claim.
- `/research-verification/experiment-design/<privateStudyId>` resumes planning.
- My Workspace links designs to their planner and preserves the paper pathway.
- Experiment Queue shows prepared jobs; original evidence remains available in
  the evidence workspace. Planning downloads include source context, versions,
  model attempts, failures, prompts, usage and hashes.

Reproduce local software verification:

```sh
# jumpserve-front-end
npm run lint
npm test
npm run build

# In another terminal, jumpserve-infra, with the isolated PostgreSQL fixture running
python3 -B test/serve_research_ideas_fixture.py --claim-design

# jumpserve-front-end; fixed loopback fixture, synthetic auth/AI/cloud dispatch
node scripts/verify-claim-design.mjs
```

The browser fixture checks the real components, API adapters, backend, agent and
SQL. It verifies queue persistence, rather than launching cloud experiments.
Actual Next.js routes are separately checked for unauthenticated sign-in returns.
A legitimate authenticated production flow and cloud execution are not verified.

No migrations, prompts, application code or infrastructure were deployed for this
implementation. Pending migrations live in `jumpserve-infra/database/20261017000*`.
The new `research-claim-design` prompt module has three retained draft candidates;
none passes the complete publication criteria. Do not bypass that gate.
