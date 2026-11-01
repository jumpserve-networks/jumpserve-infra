# Controller reconciliation and incident evidence handoff

Status: implemented and verified locally. Production requires a new explicitly
requested release, new runtime qualification and installed-source verification.

## Observed failures

The retained ordinary controller dispatch `d26fdbff-2378-5443-9999-e8b031f4d3e9`
has a failed terminal parent and an untouched queued row, with no claim fence,
receipt, artifact or native call. Both candidate discovery and worker recovery
previously required a builder payload, so the ordinary request was never offered
to the existing atomic reconciliation adapter. Its research repair diagnosis
kept waiting, and separate platform repair turns could only report the missing
proof.

For a second incident, the original context-delivery manifest and checkpoint
were already stored. The checkpoint contains the completion helper, work packet,
binding metadata and compressed native tool history. The supervisor only projected
four source/validation files and never selected the original bootstrap/manifest.
It therefore lacked the evidence needed to investigate the missing candidate
handoff. The fix supplies passive evidence; it does not claim that a successful
model response or source checkpoint proves an assessment resumed.

## Changes

- Migration `202611010007_controller_queue_reconciliation.sql` includes ordinary
  queued controller requests in discovery and atomic reconciliation. It retains
  every original row/parent lock, exact request binding, terminal-parent check,
  empty receipt/artifact/native-admission requirement and claim fence. The worker
  routes queued requests before the builder-only native cleanup path.
- Existing builder proofs remain version 1. New ordinary controller proofs use
  version 2 and an explicit request kind. The client validates both types and
  their unchanged original snapshots. Neither proof grants a refund, changes a
  parent outcome/deadline/counter, establishes container cleanup or permits replay.
  An unrelated unknown native call still stops the assessment repair.
- A private, read-only current-state diagnostic supplies exact refusal codes in
  the authorized incident packet. Eligibility is rechecked under the original
  locks before a proof is written. The diagnostic alone does not close a request.
- Migration `202611010008_repair_incident_delivery.sql` selects incident-specific
  manifests, checkpoints, receipts, bootstrap, policy and declared denied-request
  artifacts before incidental transport files. Selection remains study/task
  bound and limited to twelve delivered artifacts. Current diagnosis pointers
  and omitted original references remain visible.
- The supervisor passively decodes approved checkpoint members and verifies
  compressed history hashes, expansion size and record counts. It supplies up to
  eight recent request/output pairs, preserving original ordinals and hashes.
  Missing outputs, omitted pairs, oversized excerpts and redactions are explicit.
  Archive paths, duplicate identities and symlinks remain fenced. No archive code
  is extracted or executed; the existing credential/contact redaction applies.
- New builder manifests capture installed source hashes before provider
  admission. Context/slot refusals retain the exact received-request reference
  and normalized request hash. Historical missing fingerprints stay missing;
  current source alone does not establish which code produced an older result.

## Verification

```sh
# jumpserve-back-end
PYTHONPATH=research_workflow python3 -B -m unittest discover -s research_workflow/tests -v
PYTHONPATH=research_workflow python3 -B -m unittest discover -s platform_supervisor/tests -v
# jumpserve-infra, existing isolated loopback PostgreSQL server
python3 -B test/check_controller_handoff_database.py
# Fixed ignored diagnostic originals from the read-only production investigation
python3 -B test/check_controller_handoff_retained.py
```

The database suite runs all prior funding, repair, private-access, reconciliation,
polling and fair-admission controls unchanged before applying these migrations.
It exercises ordinary-request discovery/closure, concurrent idempotency, exact
refusals, old builder proof compatibility, unchanged uncertain outcomes, incident
artifact selection under log churn and study isolation. The retained control
verifies the original manifest/checkpoint hashes, delivered helper/work-packet
identity and the actual 504-record compressed history without running its source.
No production reconciliation, inference or database mutation occurs in these
local checks. This is implementing-agent software verification, not independent
scientific or end-to-end unattended assessment qualification.

## Release order

After an explicit deployment request, qualify the exact new backend runtime and
platform bundle with the existing dedicated AWS release process. The currently
published runtime certificate does not qualify these new bytes. Use the bounded
maintenance hold and let existing calls drain, apply both migrations, install and
verify the exact runtime/bundle sources, then release the original hold.

Observe the trusted worker closing only the eligible original queued admission,
its immutable proof and subsequent read-only repair diagnosis. Verify actual
incident delivery including hashes, helper/metadata and tool pairs in the next
platform turn. Retain the separate genuinely incomplete native stream on
assessment `444d171c-2fac-4ba9-b33c-2b46304cb0ec`; these changes do not manufacture
its terminal response or authorize replay. Preserve all existing deadlines,
category budgets, cancellation and scientific criteria.
