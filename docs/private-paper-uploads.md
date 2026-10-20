# Private PDF paper intake

This document preserves the original local implementation record. The later
production release and actual parser correction are documented in
[private-paper-upload-production-v1.md](private-paper-upload-production-v1.md).

Local implementation; not deployed by this editing request. The new-study form
accepts one PDF up to **10,000,000 bytes**, research domain and reproduction scope.
It no longer asks for a title or public URL. The filename supplies the initial
workspace title; that title is not an extracted bibliographic assertion.

The browser checks the original PDF signature, size and SHA256, then requests an
owner-scoped upload reservation at `POST /research/paper-uploads`. The backend
returns a signed, non-overwriting upload permission for one exact object in the
private `research-paper-uploads` bucket. The bucket has a 10 MB limit and permits
the PDF MIME type. Tokens are returned only to the authenticated owner and are
excluded from stored prompts, metadata, provenance and logs.

After the upload, the backend downloads and checks its complete original bytes,
copies them into the existing private research artifact repository, and verifies
the stored bytes again. One database transaction creates the private study,
original artifact, autonomous workflow, initial prompt and intake task. No work
is admitted before this verification. Requests retain the same UUID across
retries; concurrent completions create one workflow. An uncertain upload response
is reconciled by verifying the stored object rather than creating another study.
Invalid signature/hash/size rejections remain recorded; absent uploads remain
pending and retryable. Pending reservations expire after two hours, with at most
ten unexpired pending reservations per owner.

An uploaded paper has a null `paper_url` and explicit `paper_upload` identity
(`sha256`, `byte_count`, `filename`). No placeholder public URL is created.
Original bytes remain private. Legacy URL studies and unpublished ideas retain
their existing identity and replay behavior. The new upload relation has RLS,
no browser table privileges and a service-only RPC. Terminal upload identities
are immutable. Private follow-up/design workspaces may copy the original PDF
only for its owner; publishing results does not expose the uploaded PDF to other
users.

The existing bounded PDF parser reads the retained artifact without an Internet
fetch. Text extraction remains `retrieved-unreviewed`; figures, scans, equations
and supplements are not represented as fully reviewed. A retained domain campaign
can be selected only when its main-paper source matches the uploaded SHA256 and
byte count exactly. Filenames are not paper identity. The derived plan records
this match in provenance and keeps its original historical conditions and limits.

The model prompt and $100/seven-day/25-attempt defaults are unchanged. This work
adds no new scientific validation or actual model evaluation. Runtime manifest
v28 records exact local development hashes with `source_revision=uncommitted`
and the released v27 base revision. Before release, commit and pin the clean
backend revision and complete the applicable release checks. Existing actual
model evidence belongs to its original v27 profile and cannot establish a new
evaluation of the changed runtime. Synthetic local publication-guard declarations
use a separately retained historical profile, with current working-tree hashes
recorded separately; no production publication guard was weakened.

Validation performed locally:

Exact report paths and SHA256 values are retained in
`private-paper-uploads-validation-v1.json`, including failed and successful
browser attempts, both database campaigns and the original historical profile.

- 168 backend tests and 194 frontend tests passed, including file identity,
  capability gating, cross-study upload permissions and retry behavior.
- Fourteen focused infrastructure tests passed; frontend and infrastructure
  builds passed. Focused ESLint and diff checks passed.
- Eight actual Postgres/PDF upload groups passed, including three simultaneous
  completions, missing and invalid bytes, private access, actual pypdf extraction,
  legacy replay and owner-only follow-up copies.
- Eleven existing autonomous-workflow Postgres groups passed, covering limits,
  original prompts, parallel claims, reservations, ownership and bounded TCP.
- Nine browser groups passed with the actual React components, API orchestration,
  Postgres and arithmetic. Google identity, Storage transport, source/provider
  answers and wake notifications are explicitly local software fixtures. The
  actual Next.js anonymous redirect paths were checked separately.

Primary AI inspection covered the mobile light and desktop dark PDF form
screenshots. This was not human or independent review. Original failed campaigns
remain in `.test-artifacts`: the first SQL launch was sandbox-blocked; an early
fixture omitted the new private relation; historical publication checks rejected
current hashes; and the browser found a label that included its help text.
Those issues were corrected without altering historical release evidence.

The implementation was verified without production database changes, actual
model calls or cloud experiments. Remote signed upload/CORS and bucket enforcement,
a legitimate Google-authenticated request, and deployed execution remain
conditional verification gaps. Hosting and storage charges are unallocated,
not measured zero. Failed/pending staging objects are retained; no automatic
storage-retention cleanup is claimed by this change.

Reproduction commands:

```bash
# jumpserve-back-end
python3 -B -m unittest discover -s research_workflow/tests -q
# jumpserve-front-end
npm test
npm run build
# jumpserve-infra, with the documented isolated Postgres cluster on 54477
npm run test:research:paper-uploads
npm run test:research:autonomy
python3 -B bin/prepare-research-runtime.py
npm test -- --runInBand test/research-workflow.test.ts
npm run build
```

For the browser campaign, run `npm run test:research:autonomy:browser-fixture` in
infrastructure, a separate built frontend on localhost:6002, then
`npm run verify:research:autonomy` in the frontend. Its original reports and raw
fixture bytes are retained in the timestamped `.test-artifacts` directories.

Deployment order, only when explicitly requested: verify AWS account
395567831870 and Supabase project regphejnlvfpyokpniny; apply
`database/202610200001_private_paper_uploads.sql`; deploy the pinned backend and
`POST /research/paper-uploads` integration; verify private Storage permissions and
the `research-paper-upload-v1` capability; deploy the frontend; exercise a real
owner upload, retry, artifact hash readback and queue handoff. The capability gate
prevents an older service from accepting the new form as a metadata-only study.
