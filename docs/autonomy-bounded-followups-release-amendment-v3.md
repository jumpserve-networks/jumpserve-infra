# Reconcile one explicit provider rejection without resetting authorization

Release trajectory v2 reached ten attempts: nine actual model answers and one
explicit AWS `ThrottlingException`, with empty stdout and retained original stderr.
The actual controller retained attempt ten, its reservation and missing usage,
then blocked without replay. The collector subsequently tried to encode an
absent SDK message and failed; retain its report and original producer bytes.

Correct the collector to distinguish an absent answer from an empty/zero answer.
A reviewed rejection has failure provenance, not fictional raw/rendered answer
reviews. Add a publication guard for that explicit case; all actual received
answers still require actual raw/rendered review. Do not call AI absence a pass
for answer accuracy; report successful safe failure handling separately.

Permit one operator reconciliation in the isolated database only after verifying
the exact retained throttle stderr, no SDK message, blocked task, ten attempts,
two completed checks and original authorization. Preserve the failed turn and
reservation, append an audit event, and queue the same task's next numbered
attempt. Never reset the original deadline, attempts or commitments, nor replay
turn ten. Freeze the resumed profile before dispatch. Apply a 20-second spacing
before subsequent provider calls. Maximum remains 25 total attempts, $30 total
evaluation commitments and 45 minutes from the original frozen start. A second
rejection stops safely; no further reconciliation is authorized by this protocol.

This is service-operator reconciliation in a software/release evaluation, not
automatic production recovery or a browser-user action. Original candidate v8,
runtime hashes and scientific criteria remain unchanged. Missing provider usage
remains missing; its retained reservation is not an invoice charge or zero cost.
