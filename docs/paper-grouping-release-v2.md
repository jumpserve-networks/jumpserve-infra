# Backend grouping release, 2026-10-25

Scope: the private grouping RPC, paper-review API, autonomous controller and
matching OpenClaw model-worker runtime. Pending authentication and frontend
changes are excluded. Base published autonomy prompt v10 stays unchanged.

The response/storage envelope remains `paper-review-selection-v1`. The active
versioned request policy is `paper-review-selection-policy-v2`; v1 remains
retained for original request reproducibility. The revision preserves qualifiers,
separates measured observations from targets and derived predictions, and avoids
merging findings from different configurations. All suggestions retain original
source-linked statements, units and identifiers. Owner confirmation still gates
experiments. Existing inventories share their original spending/deadline limits.

Before release, six exposed development cases and the full 175-candidate TCP88
inventory were frozen and evaluated through native OpenClaw / gpt-6.1-sol with
the existing ChatGPT subscription: at most 32 provider attempts, 1,800 elapsed
seconds and four operational retries, without paid API fallback. All six cases
passed their declared checks; all 175 candidates reached one completed batch.
There were 28 successful calls, zero failed calls and no operational retries.
Available usage was 213,380 input / 30,016 output tokens (243,396 total). Charges
and subscription allocation are unknown. Final suggestions: 3 central claims,
15 findings. These descriptive counts are not accuracy estimates or uncertainty
intervals. No networking claim or historical experiment was reproduced.

The primary implementing Codex AI inspected the six actual selections/rationales
and the final eighteen selected source passages/labels. It is not independent
or human review; these are development checks, not held-out validation. Every
intermediate response was programmatically validated but not substantively
reviewed. The earlier v1 qualifier caveats and all failed calls remain retained.

Release blockers: exact clean committed backend hashes; passing controller and
native transport tests; passing isolated PostgreSQL grouping/privacy and PDF
review checks; accepted bounded model evaluation; private raw evidence archive
verified after GET with anonymous reads denied; correct AWS/Supabase targets;
no active model dispatch at worker update; reviewed stack diffs; private RPC
grants/RLS; all deployed Lambda and worker source hashes; and a real worker
grouping inference before resuming admission/polling. That inference uses the
frozen synthetic qualifier case, creates no assessment and runs no experiment.

Conditional checks: a fresh production PDF upload through extraction, grouped
review and owner confirmation needs a new assessment. The user separately asked
to clear all 31 existing paper assessments; release verification must not
recreate one. No frontend deployment is authorized by this backend-only release.
The production Previous Assessments empty state was observed in a legitimate
signed-in browser after the reset; four research ideas were retained.

The reset backed up and verified 60,310 rows (95,071,235 exported bytes), tested
the deletion under rollback, then committed a matching scoped transaction.
Foreign keys and RLS remained active. Delete guards were suspended only under
table locks inside that transaction and restored before commit. All non-target
research records were hash-checked unchanged. Private raw Storage objects were
retained. Backup and receipts are in the original infrastructure checkout at
`.test-artifacts/assessment-reset/20261025T225026860119Z/`.

Use `bin/paper-grouping-release.py` for guarded archive, migration, stack
previews/deployment, worker update, real worker inference and verification.
Temporarily hold admission and polling with the existing OpenClaw release
helper. Deploy the inactive backend and worker, verify sources/inference, then
activate both admission and polling through CloudFormation so desired and live
configuration agree. Preserve prior ZIPs, RPC definitions, worker backups,
failed receipts and exact private model artifacts. Do not reuse a failed
publication judgment as approval for a different policy hash.
