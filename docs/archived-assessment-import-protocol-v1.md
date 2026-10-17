# Archived paper assessment import — protocol v1

Declared 2026-10-10, before any import writes or publication. This is a data
integration campaign, not a new scientific experiment. Five existing assessments
are in scope: propagation delay, LEO emergency failover, HTTP/2 compliance,
IPv6 DNS and ReliableSketch. Their detailed measurements already exist in the
module-specific JumpServe Supabase relations.

## Questions and scope

Can all five appear in Research Verification's existing public assessment pages
with truthful provenance, separate published values and recorded results, and
visible scientific limits? Can the existing scientific records and private
originals remain intact?

Add five explicitly imported historical catalogue entries. Preserve the existing
IPv6 owner workspace, follow-ups, preparation fixtures and queue jobs unchanged.
The historical IPv6 entry reflects its original module assessment; later owner
workspace attempts are a separate campaign and must not be silently combined.
Import all direct-source and claim register rows, original method declarations,
configurations and aggregate summaries. Show key numeric summary results in the
shared model. Detailed per-observation rows stay in their original relational
tables and remain linked through the existing domain module and its exports.
The shared export must identify this scope rather than claim to contain every
packet, trial, stream key or source PDF.

## Provenance and design

Stable IDs derive from module, record kind and native record identity. Imports
are append-only, hash-checked and reject changed replay bytes. Original experiment
dates, missing values, units, seeds, limitations and review declarations remain
in retained database exports. Database row creation is the import date, not the
original experiment date. New protocol wrappers have registration_kind
retrospective-import and retain original protocols as data. They do not establish
prospective registration of old experiments.

The new run records the actual transfer/validation of an assessment register;
it is a source-review/import audit, not a rerun of the historical experiments.
Historical run counts and outcomes are reported explicitly as native records.
No queue execution, experiment timestamps, human review, measurement, uncertainty
interval or missing cost is invented. The original native records are the primary
scientific evidence. Source records labeled merely "reviewed" without an explicit
complete-reading scope are conservatively partial; retain the original declaration.

Known explicit historical assessment labels map directly to reproduced,
discrepant, inconclusive and untested. Where only coverage is recorded, use a
documented conservative mapping based on existing summaries and reports; never
upgrade broad claims from a narrower successful result. Preserve original
coverage text alongside the mapping. Unresolved claims require current gap rows.

## Limits and stopping

Only AWS account 395567831870 and Supabase regphejnlvfpyokpniny are allowed.
The owner is taken from the already authorized IPv6 workspace without logging
the owner's identifier or credentials. No auth session is fabricated. Trusted
operator integration is not an authenticated browser request.

Budgets: five papers, at most 5,000 shared records per paper, 3 MB scientific
snapshot per paper (4 MB existing API hard bound), at most 10 MB per stored
database-export artifact and 50 MB aggregate logical originals. Database writes
use existing server-only immutable RPCs in batches of at most 100 records.
Original snapshots/manifests, validation failures and receipts are retained.
Stop rather than truncate, fill missing values or rewrite original records when
schemas, hashes, labels, identities, ownership or budgets do not reconcile.
No inferential statistics are computed for this transfer. Existing source
uncertainty and dependence declarations are preserved verbatim.

## Publication criteria and verification

Before public publication, verify record schemas, expected coverage, link and
foreign-key identities, summary conservation, label mapping, missing/zero
distinction, numerical units, round-trip stored hashes and every imported field.
Verify existing RLS, browser write denial, private artifact bucket and service-only
writers. Verify public page/JSON availability for each original module and
exercise the shared display with exact prepared data in desktop/mobile views.
Check source-scope and software judgments explicitly; identify the reviewer as
the AI implementer, not a human or an independent scientific reviewer.

Publish only through existing research_publish after both declared reviews pass.
Incomplete scientific coverage is allowed when its labels and gaps are visible.
After publication, verify anonymous public catalogue, full shared-snapshot
coverage, exports and production pages. Retain publication history. No frontend,
backend or infrastructure deployment, schema migration, prompt/model change,
new experiment or automatic claim reassessment is authorized by this import.
Authentication browser testing remains conditional; this task uses a trusted
operator. Data publication and scientific scope are reported separately.

Usage: record measured transfer bytes, stored payload bytes and wall times where
available. Database overhead, hosting, workstation, model orchestration and
unreconciled charges remain unallocated/missing, not zero.
