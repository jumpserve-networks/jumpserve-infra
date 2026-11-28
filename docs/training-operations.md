# Synthetic training operations

`JumpServeTrainingOperations` adds fixed Systems Manager documents to the
existing synthetic training coordinator. The IAM Roles Anywhere profile
`jumpserve-training-automation` reads the private diagnostic receipts and can
invoke the diagnostics document on that coordinator. A separate GitHub OIDC
role can publish source archives and invoke the release document from
`jumpserve-networks/jumpserve-front-end` on protected `main`. The coordinator
executes both operations as `ec2-user`.

## Initial deployment

Use the `CoordinatorInstance` and `TrainingBatchBucketName` outputs from
`JumpServeSyntheticBatchCoordinator`. Render the stack with
`python3 -B bin/render-training-operations.py`, then deploy it in `us-east-1`
with those two parameters and `CAPABILITY_NAMED_IAM`. The stack owns the AWS
IAM provider for `token.actions.githubusercontent.com`. If the account already
has that provider, import or reference it before creating the stack.

Set the frontend repository Actions variables
`JUMPSERVE_TRAINING_COORDINATOR_INSTANCE` and
`JUMPSERVE_TRAINING_BATCH_BUCKET` to the same stack outputs. The coordinator
requires SSM Agent version 3.3.2746.0 or later for parameter interpolation.

## Diagnose and recover

Invoke `JumpServeTrainingBatchDiagnostics` on the coordinator with the AWS
profile `jumpserve-training-automation`, a numeric `BatchId`, and a unique
`RequestId` of 32 lowercase hexadecimal characters. Read the receipt at
`diagnostics/<batch-id>/<request-id>.json` in the training bucket. The receipt
includes allowlisted per-paper failure codes and worker lease status. It omits
raw journal text, contents of evidence and credentials.

For one outstanding lease, use a new request ID and supply `Mode=recover`,
the exact `Paper` identifier and `Stage=generator` or `Stage=verifier`. The
document acquires the batch lock, confirms the batch is terminal, checks the
lease identity against the journal and invokes the existing lease cleanup
helper. Check the recovery receipt before starting a replacement batch.

## Release

Dispatch the frontend's `training-runtime-release.yml` workflow on `main`
when the coordinator is idle. The workflow packages the protected commit,
uploads a content-addressed archive and verifies the coordinator's receipt.
The installer checks the digest, takes the batch lock, and atomically switches
the active release. It retains the previous release and reuses the existing
benchmark inputs and dependency directories from their original release.
Dependency changes require provisioning the matching dependencies on the
coordinator before activating that release.

The receipt key is `runtime/receipts/<workflow-run-id>-<attempt>.json` in
the training bucket. If a request times out, read its receipt before issuing a
replacement. A `coordinator_busy` receipt means a batch held the lock during
the release window. Dispatch the release again after that batch finishes.
