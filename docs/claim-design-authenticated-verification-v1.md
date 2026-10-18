# Authenticated production verification: adoption blocker

2026-10-18 UTC. This report is a retained checkpoint; a later successful follow-up
must not overwrite the original failure. The declared methods and budget are in
[protocol v1](claim-design-authenticated-verification-protocol-v1.md).

| Boundary | Observed result |
| --- | --- |
| Legitimate Google session → private claim workspace | Passed through the production browser and normal APIs. No session token was exported or user impersonated. |
| Actual planning → Bedrock → persisted attempt | Two complete `research-claim-design-v6` calls: source-specific clarification, then exact reuse of the supplied saved pilot. |
| Owner configuration → private Storage | Authenticated compile stored 399 original bytes, SHA-256 `a0c00449a809ff1e67c2b3e3ef48e4eacaa6652f67bd65ab6bbdbe46b948188a`. Backend retrieval verification and a separate administrative retrieval matched the exact browser text. Anonymous read was denied. |
| Saved pilot → adoption | Failed: normal UI adoption returned HTTP 503. Three draft versions and both model answers remain preserved. |
| Fresh reviews → readiness → queue → cloud execution | Not attempted past the adoption failure. No campaign, queue job, VM or measurement was created. |

The chosen paper claim concerns BBRv1 delay sensitivity. The owner-supplied pilot
is explicitly an acquisition check with one configuration and two small transfers;
it cannot resolve the original hypothesis. Its original source and partial-review
status are preserved. No scientific claim label or original assessment changed.

## Demonstrated mechanism and proposed correction

The persisted reuse proposal equals the current saved packet. It remains exactly
equal after the released API's configuration-hash compilation. The live catalog
definition of `research_save_idea_packet` rejects an unchanged new version, with
the message that a review attempt cannot reset its budget using identical content.
The released adoption handler tries that forbidden insert. Isolated SQL regression
testing reproduces the guard rejection. The production API suppresses the detailed
database error; the observed HTTP response alone would not establish this cause.
The catalog representation hash is
`c1874a8f7c390fe3b70e62c641c5008460a8ff4081de45b0fd7217a6c458a788`.

The local correction retains the existing packet/version and records an immutable,
idempotent owner reuse audit event. It does not create reviews, acceptance,
readiness, campaigns or measurements. The new service-only RPC validates owner,
current packet, complete compatible source-bound model answer, exact proposal,
published prompt and policy; browser execution remains denied. The frontend labels
that action **Use this saved plan** and explains that version and review budgets
remain unchanged. Changed proposals retain the existing new-version path.

Pending migration:
`database/202610180001_claim_packet_reuse.sql`. The change is local and uncommitted;
no migration, application deployment or main-branch push was performed in this
verification turn. The scoped CDK diff changes only the shared research runtime
code in five existing Lambda functions; no route, IAM or infrastructure replacement.
The agent prompt and model-facing source bytes are unchanged.

Local checks passed: 123 backend tests, 180 frontend tests, frontend lint/build
(one existing auth-button warning), 89 infrastructure tests/build, seven
claim-design SQL groups, eleven existing-idea SQL groups and eleven browser
groups. The new regression verifies reuse and retry without a duplicate packet,
preserves unaccepted readiness and existing review gates, and checks browser RPC
denial. Browser authentication/provider/cloud dispatch in those local tests are
explicit fixtures; they are not relabeled as production execution.

## Usage, artifacts and limits

The two actual provider calls used 15,621 input and 490 output tokens, with
recorded wall times about 5.115 and 1.386 seconds. Measured/estimated charges,
authoring/reviewer model usage and storage allocation remain unknown, not zero.
There were zero campaign launches and zero experiment instances. Provider attempt
records and raw response hashes remain in Supabase; local private originals and
read-only collection receipts are under `.test-artifacts/claim-flow/v1/`.

An initial automated bulk form fill submitted unchanged empty fields and was
correctly rejected. Native keyboard events resolved that automation problem;
subsequent authenticated saves succeeded. This is separate from the reproducible
unchanged-plan adoption defect. A sandbox access failure and a collector syntax
error are also retained in the session record; no scientific result is inferred
from them. Decoded browser request/response bodies were collected without headers
or credentials. Earlier requests predate that capture and are identified as such.

Evaluation and operational review are by the primary Codex AI implementer;
no human, independent scientific or held-out review is claimed. Execution remains
unverified pending the production correction and continuation of the bounded
pilot. Real-world topology and custom-package runners are outside this campaign.
