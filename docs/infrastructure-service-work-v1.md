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

The fixed release role also needs `s3:ListBucket` on its existing asset bucket.
S3 returns 403 for a nonexistent object without that bucket permission, preventing
the broker from recognizing first use of an immutable staging key. This grant
adds no bucket mutation, deletion, other-bucket access or static credentials.
See [the S3 GetObject permission contract](https://docs.aws.amazon.com/AmazonS3/latest/API/API_GetObject.html).

`202611060001_service_repair_lifecycle.sql` records activation consumption in a
private immutable relation. It backfills earlier consumption from retained
activation/checkpoint and resume-event evidence, so an old successful service
cannot reopen a later dependency wait. A different request can still resume
its parent once after its own confirmed operation and verified release.

Completed parser recovery closes only the exact intake incident. Closure requires
the original failure hash, qualified service activation and release, matching
original/source/text artifacts, finished contiguous source chunks, ready review
selection, and completed controller/dispatch responses bound to retained artifact
hashes. Missing or uncertain evidence keeps the incident open. No claim scope,
measurement, research outcome, reservation, deadline or original attempt changes.
Existing owner confirmation is retained; preparation does not establish a
scientific finding.

Repair roots include bounded continuation attempts. Unnecessary dependencies
retire through cancellation rather than being certified as installed fixes.
Active work stops at its existing boundary; uncertain original calls and
operations remain available for reconciliation. Unrelated incidents and completed
service tasks retain their outcomes.

The matching backend change gives each derived service candidate an identity
bound to its immutable request and base revision. Rebase retains the superseded
candidate and uses a distinct record. A retained checkpoint from the earlier
identity scheme can recover only after its original candidate is superseded and
any original PR closure is confirmed. Pending or uncertain publication prevents
replacement; historical patches and receipts are not overwritten.

Run `npm run test:platform:service-lifecycle` for the isolated database chain and
`python3 -B -m unittest discover -s platform_supervisor/tests -q` in the backend
for controller regressions. The database entry point retains the existing service
suite before applying the lifecycle migration. Local iteration may use
`-- --reuse-base`; that mode verifies every baseline migration hash before cloning
the isolated fixture database. CI always builds a fresh baseline. The SQL and
backend fixes remain compatible with the existing service-work contract and can
be released independently through their qualified deployment paths.
