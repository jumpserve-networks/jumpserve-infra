# Implementation amendment v2 — 2026-10-07

Retain `research-workflow-implementation-v1.md` unchanged. During implementation,
add bounded operator commands for original-resource retrieval, page-referenced PDF
text packets, paper intake and protocol freezing. Text extraction remains
retrieved-unreviewed and does not establish bibliography or figure review.

Strengthen publication checks: scientific and software reviews capture their
evidence manifest at recording time. New evidence requires new reviews; passing
old review IDs cannot publish unseen drafts. Snapshot reads validate record
membership and publication identity to reject mixed-version exports.

Unexpected observations are preserved separately from planned observations;
summary counts conserve planned + unexpected observations. This is a software
accounting correction, not a change to the original IPv6 findings.

The research API is an explicit CDK context option, `researchWorkflowEnabled`.
Existing infrastructure tests and environments do not gain new resources
implicitly. Deployment must apply the migration, prepare the verified runtime and
enable the feature together. No production changes are authorized by this
implementation-only turn.
