# Paper review authors

`/research-verification/new-assessment/<id>` includes an optional Authors field
directly below Title. It starts with the extracted byline, accepts one name per
line and saves the ordered names with owner confirmation. Empty input records an
explicit unknown byline. Names support Unicode and punctuation, including commas.
The bound is 100 names of at most 200 characters each. Confirmed metadata is
read-only, matching the existing title and domain fields.

`research_paper_reviews.metadata.authors` retains the original extraction.
`metadata.owner_authors` records the versioned owner correction, actor and request
revision in existing private review history. Public and owner assessment listings
project only the effective names. Clearing the field never restores extracted
names through the title endpoint's PDF fallback. Scientific claims, original
source bytes, funding, deadlines and selected statements are unchanged.

The `paper-review-authors-v1` marker identifies support in review responses. Older
responses still render the field read-only and keep their original confirmation
contract. The backend checks the installed SQL capability before any confirmation
containing authors, so a missing migration cannot silently discard the edit while
starting claim work.

For an explicitly requested release, apply
`database/202611050002_paper_review_authors.sql` before releasing the updated
backend API and frontend. Qualify and update the backend runtime pins for that
release; the existing intake and general runtime pins remain unchanged by this
local feature work. The migration wraps the existing confirmation function rather
than changing scientific or authorization checks. Concurrent exact retries are
idempotent; conflicting edits, stale revisions, cancellation and invalid names
leave no partial author correction.

Checks: `npm run test:research:paper-authors` runs actual isolated PostgreSQL
transactions without cloud or provider calls. Backend paper-review/catalogue
tests cover validation, capability checks and projections. Frontend unit tests
and `npm run verify:paper-uploads` check field position, prefill, ordered edits,
confirmation payload, reload, and desktop/mobile rendering.

## Assessment UI API release

`research-api-runtime.json` separately pins the HTTP API. Prepare it with
`python3 -B bin/prepare-research-api-runtime.py` against that exact backend
revision; CI checks out this pin independently of the general worker runtime.
The API asset is hash-checked during synthesis. Existing worker and executor
runtime pins, roles, settings and source qualifications remain intact.

The fixed `bin/assessment-ui-release.py prepare` stages a reviewed change set
from the actual deployed template, updating only the API code and adding the
assessment detail and prompt GET routes with their matching invocation grants.
It refuses unrelated changes or a non-settled stack. Inspect that change set
before executing it; `check` compares the installed template and actual Lambda
ZIP bytes with the retained source manifest. Release evidence is retained in
`.test-artifacts/assessment-ui-release-20261105/`. The author migration runs
before this API release, and the frontend follows verified API installation.
