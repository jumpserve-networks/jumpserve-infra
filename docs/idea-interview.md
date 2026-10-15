# Idea-specific conversational planning

Published and deployed on 2026-10-15 with research-ideas-v11; see
[the production release report](idea-interview-production-release-v1.json).

Current follow-up: source-faithful reviews and the eligible unpublished v11
candidate are documented in [idea-review-source-fidelity.md](idea-review-source-fidelity.md).
The original v1 validation report remains a historical record of the earlier
blocked candidate; it is not overwritten. Current evaluation uses
`python3 -B test/evaluate_research_ideas.py --live --source-review` with 21 cases.

The idea workspace defaults to an explicitly started AI conversation. Opening or
reloading it requests no model response. Each generated question names one allowed
plan field. Sending an answer saves the owner's exact words as a new immutable
packet, then requests one next question against the confirmed packet identity.
Asking the guide for advice does not save an answer. Earlier versions, AI outputs,
failed/invalid attempts, prompt identities, context and usage remain recorded.

The guide can select the next field or revisit an ambiguity; choosing a saved
field explicitly constrains the response to that field. Invalid routing cannot
revive an earlier usable question. Unconfirmed requests keep their original IDs
for idempotent retry. Older agents fail the interview capability preflight;
the existing checklist remains available. Planning cannot approve or run anything.
Fresh comprehension and critic reviews, exact packet acceptance, frozen execution
configuration and explicit queueing retain their existing guards.

The backend selects the module's existing authenticated prompt/persistence path.
The current `idea-task-prompts-v2` template is stored in `agent_prompt_versions`
as a versioned JSON string; the backend also accepts the earlier v1 schema.
Only the task's selected system text reaches the model.
Its exact text/hash and the complete stored prompt hash are retained in immutable
attempt provenance. Conversation responses use a formatting-only channel with
`summary`, `question`, and an enumerated `field`. Its normalized stored planning
recommendation always remains `needs-clarification`, never readiness approval.
The routing field is read from the preserved validated provider message; the
database's original-attempt immutability guard remains unchanged.

Limits: 24 KB research messages, 2,048 output tokens, one model call per requested
turn, no automatic retries; existing SQL caps of 200 calls/study, 12/session and
three attempts/review task/packet still apply. The UI rotates short planning
sessions with the full saved plan. If necessary the backend omits oldest complete
history pairs to fit the research-message budget and records the omission count.
Original turns remain in the database. System/schema input is additional. Provider
tokens and wall time are retained; unavailable monetary charges remain null.

Run frontend checks from `jumpserve-front-end`:

```sh
npm test
npm run lint
npm run build
```

With the isolated PostgreSQL test cluster on port 54477, run from
`jumpserve-infra`:

```sh
npm run test:agent
npm run test:research:ideas
npm run test:research:ideas:browser-fixture
```

While that fixed loopback fixture is running, run browser campaigns sequentially
from `jumpserve-front-end` (they share the fixture's observation counter):

```sh
npm run verify:research:ideas -- --interview
npm run verify:research:ideas -- --guided
```

Set `JUMPSERVE_BROWSER_CSS_PATH` if the production build styles are in an isolated
checkout. Browser fixtures replace authentication and the provider, while using
actual components, API handlers, agent parsing, PostgreSQL and fixed loopback
HTTP measurements. They establish software behavior, not generated answer quality.

The bounded actual-answer evaluator requires the verified JumpServe AWS profile:

```sh
python3 -B test/evaluate_research_ideas.py --live --source-review
```

The criteria and original frozen cases precede evaluation. Amendments preserve
failed candidates and actual responses. Review is by the AI implementer, not a
human or independent reviewer; reused/tuned cases are not held-out validation.
See `idea-review-source-fidelity-validation-v1.json` for the passing local
candidate. `idea-interview-validation-v1.json` preserves the earlier failed
candidate and does not describe the later production release.

The local implementation made no production changes. The separately authorized
release verifies account `395567831870` and Supabase `regphejnlvfpyokpniny`,
apply the additive draft/guard migrations in order, deploy the compatible agent
while retaining the existing active prompt, publish only an eligible exact
candidate through the guarded existing prompt RPC, then release the frontend.
Earlier failed candidate seeds remain unpublished. Do not point the generic chat
handler at the JSON task template; idea requests use `research_ideas.handle`.
Verify the real Google-authenticated conversation and production persistence after
that release; those boundaries are conditional local verification gaps.
