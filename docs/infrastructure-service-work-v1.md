# Infrastructure-owned service repairs

The supervisor previously translated every capability request into a backend-only
tool-pack task. A service prerequisite consequently had no editable owning
repository and could create another dependency instead of implementing the
missing integration. Passive infrastructure references did not fix assignment
or provide a deployment adapter.

`platform-service-work-v1` adds a separate, typed handoff in the existing retained
`progress.json`. Its current fixed profiles are `assessment-evidence-v1` and
`intake-parser-recovery-v1`. The controller also recognizes the exact retained
missing-`pypdf` failure and requests its adapter without another model call.

The service broker creates one linked `jumpserve-infra` task. The parent keeps its
original repository scope, deadline, cancellation state and reservations. Service
edges participate in existing assessment bindings, ancestor cancellation and
family accounting. Repeated request acknowledgments reuse the original child;
unknown calls and external operations remain fenced.

The controller derives only `services/<request-id>.json`. The manifest cannot
contain commands, SQL, credentials, another task identity or executable source.
Its exact contract is checked before publication. Existing protected branch CI
still runs, and the normal infrastructure release workflow checks the manifest
before obtaining renewable GitHub OIDC credentials. Its fixed service adapter
executes under the original deployment operation; ordinary infrastructure
releases continue through their existing CloudFormation path.

The evidence profile reads the actual task-bound schema and hash-verifies retained
failure artifacts. Delivery distinguishes column names from private storage
locations and supplies redacted failure details, source identities and review
state to the coding workspace. No anonymous SQL grants are added.

The parser recovery profile verifies every installed dedicated-intake file,
every pinned parser module and the service startup check through a durable SSM
command. It runs the actual PDF parser as the service user. A lost command
acknowledgment is reconciled; no replacement command is sent. The cloud service
then parses the retained original PDF with the same hash-pinned parser and
existing bounded extraction code. Derived text is staged immutably under the
original operation, persisted to Supabase and read back before resumption.

Only an unconfirmed, marker-only, zero-call intake failure can resume. It reuses
the existing source instead of rewriting its immutable acquisition record.
Partial work, uncertain calls, claims, stopped assessments, expired deadlines,
unhealthy/stale worker state and exhausted recorded limits prevent recovery.
Original failures, deadlines, counters, scope and scientific criteria remain
unchanged. The transaction queues preparation; it cannot confirm claims or
manufacture measurements.

An activation receipt alone does not wake a parent. The original operation must
also be confirmed and its exact infrastructure revision recorded as verified.
Eligible parents then resume once, with their old local stop retained privately.
Unsupported service profiles are explicit implementation work; this release
does not certify universal autonomous repair or grant candidate-authored SQL.

Qualification uses actual isolated Postgres admission/resumption tests, existing
supervisor checks, new handoff regressions and release identity/acknowledgment
tests. Production qualification additionally requires a real infrastructure
child, protected merge, executed service receipt and observed assessment
continuation. Local synthetic receipts are not production evidence.
