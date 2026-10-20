# Private PDF upload production release

The new form is live at https://jumpserve.quaint-lab.org/research-verification/new-study.
It accepts one private PDF up to 10,000,000 bytes, research domain and reproduction
scope. Title and public URL fields and the previously removed introductory
paragraphs are absent. The filename supplies the initial workspace title.

Frontend `cc03ebfa33042fd4a4856a1faf8f5c1fcd24f6e3` passed Amplify main job 118.
Backend `a2db37f29231ee924dc2e825bc51df4ebb1b3f1d` is pinned by runtime manifest
v29. The migration and backend release used AWS account 395567831870 and Supabase
project regphejnlvfpyokpniny, with identity verification before mutations. Scoped
deployment retained existing stack parameters and the benchmark AMI. Active AI
prompt pointers, including published autonomy v8, did not change.

All 169 backend, 194 frontend and 93 infrastructure tests pass. Frontend and
infrastructure production builds pass. Lint has no errors and one existing
auth-button warning. Eight actual Postgres/PDF upload groups passed again after
the parser correction. The earlier eleven autonomy database and nine browser
groups remain retained development regressions, with their fixtures and exact
input hashes documented separately.

The actual production check found and corrected a defect. The first private
control, `8605412f-f912-40fa-8747-cfcd2d6aabf2`, uploaded successfully and preserved
its original and initial prompt, but the parser child could not import pypdf.
Lambda's parent interpreter had the layer on sys.path; its new subprocess did
not inherit that addition. The correction explicitly forwards the trusted parent
import path, retaining the fixed command and extraction limits. A new regression
and real local pypdf integration without a PYTHONPATH fixture cover this boundary.
The failed workflow, original diagnostic and v28 profile are preserved.

The separate follow-up, `f20e4b43-6df3-4a50-bf3b-15b01d37c2dc`, passed through the
actual signed-in production form, API, Supabase signed upload, private raw storage,
atomic intake and deployed PDF subprocess. Its 431-byte blank original has SHA256
`41ca0ee1d6ec3a96190266e38063a2c20b7a9cea652eb73f395d461f62244077`.
Readback verified both original and derived artifact hashes. The derived packet
names pypdf 6.19.0 and page 1 as `missing-text-layer`. One workflow and one intake
task retain the initial prompt with SHA256
`db66501e5e33f93bbe7f105c2c09e40b8f8858b88176df90b6db606a124d1261`.
Replaying reserve and start returned the same study, with no duplicate workflow.
The controller recorded zero model turns and correctly stopped with no
source-grounded candidate claims and incomplete coverage. This is a software
control, not a paper assessment or scientific finding.

Actual Storage checks verified signed PUT and exact-byte GET, anonymous read
denial, overwrite denial, MIME rejection and a 10,000,001-byte rejection. A normal
authenticated owner request without a signed permission also could not read the
private staging PDF. Catalog checks retain RLS, browser write denial and
service-only upload RPCs. All declared files in the deployed research API,
autonomy, queue and package-handler ZIPs match the committed manifest.

Production browser checks covered public entry/results/methods, archived IPv6
results, desktop/mobile themes, login return paths and explicit missing-data/404
exports. The new form was checked at 1365 and 390 CSS pixels in both themes;
the follow-up queue was checked in desktop dark and settled mobile light views.
No horizontal overflow or application alert appeared in those settled views.
Primary AI inspection examined the desktop dark and mobile light form and queue
screenshots. This was neither human nor independent review.

The connected browser's file-path tool rejected both repository roots. Following
the recorded amendment, the frozen original was assigned as a browser File to
the real input, then submitted using the actual form button. No Google identity,
API, Storage or parser response was mocked. The production OS file-picker dialog
was not tested. Original failed automation observations remain retained: literal
DevTools arguments were interpreted as element identifiers, and the first mobile
queue screenshot preceded completion of its real data load. The settled follow-up
and original loading state are separate artifacts. A stale-profile session probe
in the public-check script reported no session; the actual connected Chrome
session and successful authenticated API calls supersede that probe for this
release, without editing its original report.

This release does not provide fresh actual-model evaluation of v29 or a full
scientific assessment from a text-containing uploaded paper. Scans, figures,
supplements and OCR remain limited by the documented acquisition pipeline.
Published scientific assessments were not reclassified. Both controls are private,
explicitly labeled synthetic records, with no new experiment instances or model
calls. The $5.05 and $5.10 recorded control commitments are conservative admission
reservations, not measured charges. Hosting, local compute, database and storage
charges are unallocated; missing invoice costs remain null.

Machine-readable evidence and exact receipt paths are in
`private-paper-upload-production-v1.json`. The private original-evidence archive,
retrieval verification and SHA256 are recorded separately in
`private-paper-upload-production-artifacts-v1.json`. Original protocols and their
two amendments remain separate from results.

Release reproduction follows the fixed-target `bin/private-paper-release.py`
modes: inspect, migrate (once), diff, deploy, activate, verify, storage,
control-read and frontend-status. The parser correction uses the separately
recorded repair deployment. Do not reapply the migration or create controls merely
to inspect this release. `verify` and `control-read` read the retained deployment
and fixed follow-up control. Local test commands remain in
`private-paper-uploads.md`; the full infrastructure suite uses
`JUMPSERVE_BACKEND_CHECKOUT=/Users/Shared/allstar/jumpserve-back-end npm test -- --runInBand`.
