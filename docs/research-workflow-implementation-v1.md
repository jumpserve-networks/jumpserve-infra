# Research verification workflow — implementation protocol v1

Frozen implementation scope, 2026-10-07. This implements the accepted workflow
report; it does not claim that one generic experiment can validate every paper.

## Deliverable and boundaries

- A shared Research Verification module: public published assessments and exports;
  Google-authenticated paper intake and owner-scoped draft editing.
- Supabase relational records for exact sources, claims, frozen protocols,
  configurations, campaigns, runs, measurements, summaries, published values,
  assessments, evidence gaps, reviews, publications and private artifacts.
- Append-only evidence and publication snapshots. Later drafts must not become
  public merely because an earlier version of the study was published.
- A bounded backend API and operator CLI in jumpserve-back-end. The first runnable
  adapter performs matched numerical comparisons, preserving units, identities,
  missing states and declared tolerances. Other domains supply registered
  implementations or import documented external campaigns; no arbitrary shell
  execution or automatic causal conclusions.
- An explicit bridge for the existing IPv6 assessment, preserving its original
  evidence and creating actionable unresolved-claim records without changing labels.
- AI assistance uses existing study chats when available. A new generic model
  prompt is not silently enabled without its own predeclared answer evaluation.

## Release-blocking local checks

1. Backend tests: input and protocol validation, matching, zero/missing/invalid
   handling, budget stops, failed-run preservation, authenticated ownership,
   idempotency and public/private projections.
2. Isolated Postgres migration tests: foreign keys, immutable evidence,
   append-only assessments, publication manifests, RLS and denied browser writes.
3. Frontend tests, lint and production build; public empty/unavailable states,
   completed assessment, comparisons, gap queue, exports and sign-in return paths.
4. Desktop/mobile browser inspection in light/dark themes; no console or hydration
   errors; no public artifacts or identities accidentally exposed.
5. CDK build and assertions: research API only receives its required secret access,
   bounded concurrency/memory/time and no experiment-launch or model permissions.

## Conditional checks and deployment

Remote Supabase migrations, AWS deployment, a real Google session and deployed
end-to-end requests require their relevant credentials and explicit deployment
authorization for these changes. This turn authorizes implementation, not a
production deployment. Local database and browser fixtures must be labelled as
software verification, not new scientific measurements.

Scientific discrepancies do not fail software checks. Incomplete scientific
coverage can be published with visible scope and gap records. Publication requires
documented review and release checks, not that every claim is reproduced.

## Evaluation and amendments

Development cases exercise actual bounded numerical outputs and user flows.
They are not held-out scientific or model validation. Reviewer: primary Codex
assistant, AI, implementer, not independent. Preserve failed checks and this
protocol; record corrections in the validation report rather than rewriting it.

Compute and storage usage should record measured bytes, wall time and known
resources. Model usage and reconciled charges remain missing when unavailable;
missing usage is not zero cost.
