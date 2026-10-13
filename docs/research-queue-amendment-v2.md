# Queue implementation amendment v2

2026-10-07, development regression failure before release. The original queue
protocol v1 is unchanged. The worker persistence test exposed a pre-existing
validator defect: `observation_id` was classified as a UUID foreign key because
its name ends in `_id`. Domain observation identities such as `date-1` are text,
as declared in the relational schema. Exclude this field from UUID validation;
retain nonempty text validation and exact matched observation identities.

This correction applies to original and queued numerical persistence. Preserve
the failed regression receipt and recheck matching, missingness, storage and
database behavior. No published numerical value or scientific assessment changes.
The defect in this working-tree validator does not establish which code produced
any previously published results. Reviewer: primary Codex AI, implementer,
not independent. No held-out or human review is asserted.
