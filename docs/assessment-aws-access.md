# AWS access for local JumpServe assessments

The plugin starts temporary CloudFormation testbeds in account
`395567831870`. This access stack provides the IAM roles for client-driven
provisioning, workload execution and expiration. The local client owns
experiment instructions, run state, evidence collection and recovery.

## One-time account setup

An account operator deploys [assessment-aws-access.json](../assessment-aws-access.json)
as a standalone CloudFormation stack with named IAM resources. Verify the
operator profile's account through STS before deploying the template.
Supply the following parameters.

- `OperatorPrincipalArn` is the approved user or IAM role that assumes
  `JumpServeExperimentClient`. For federation use the IAM role ARN from
  the account rather than its temporary STS assumed-role ARN. Grant the
  principal `sts:AssumeRole` on that client role where required.
- `ExperimentResourcePolicyArn` is a customer-managed IAM policy in this
  account. Grant the CloudFormation execution role the service actions and
  resources needed to create, describe and delete the approved types of
  temporary infrastructure. Scope mutation to experiment resources; use
  tag-on-create conditions and resource tags where each service supports them.
  Keep permissions over shared resources read-only when needed for discovery.
  For instance profiles and similar dependencies, prepare the required
  `JumpServeExperimentWorkload-*` roles and grant narrowly scoped PassRole.
- `ExperimentDriverPolicyArn` is optional. Use it when the trusted local
  driver needs an API such as Systems Manager to reach experiment machines.
  Limit its permissions to the relevant experiment resources.

For the synthetic batch in `us-east-1`, deploy
[assessment-ec2-workload-access.json](../assessment-ec2-workload-access.json).
The worker resolves the public Amazon Linux 2023 x86-64 image from the regional
AMI parameter. Use the stack's `ExperimentResourcePolicyArn` and
`ExperimentDriverPolicyArn` outputs when deploying the access stack. Its
`JumpServeExperimentWorkload-SSM` profile is attached to the temporary workers.
The resource policy permits the bounded worker instance sizes, encrypted volumes,
and batch-tagged VPC resources. The driver policy limits Session Manager to
those workers and the AWS SSH session document.

The client role provisions and observes prefixed stacks and schedules.
Its CloudFormation delete permission requires the experiment ownership tag.
The expiration role can only request deletion of prefixed and tagged stacks.
CloudFormation uses its assigned execution role to remove the resources.
Keep the role policy available until all experiment stacks are gone.

Configure an AWS CLI profile using the approved source profile. For example,
when `jumpserve-operator` resolves to the approved non-root principal, use
this in the local AWS CLI configuration.

```ini
[profile jumpserve-experiment]
role_arn = arn:aws:iam::395567831870:role/JumpServeExperimentClient
source_profile = jumpserve-operator
```

Confirm the resulting account and role with
`aws sts get-caller-identity --profile jumpserve-experiment`.
EventBridge Scheduler and CloudFormation must be available in every selected
Region. The scheduled deadline requests a standard stack delete, so
deletion protection and dependencies that prevent deletion must be addressed
in the experiment design.

## Private synthetic batch coordinator

The production `JumpServeSyntheticBatchCoordinator` stack in `us-east-1`
defines the coordinator, encrypted sign-in volumes, and private batch progress
storage. The coordinator assumes the experiment-client role. Set
`BatchCoordinatorRoleArn` on the access stack to the coordinator stack's
`CoordinatorRoleArn` output. Preserve the operator principal and workload
policy parameters on updates.

With `EnableWebBatchStart=true`, the coordinator stack grants the frontend
role access to the numbered start document on the coordinator only. Deploy
[the stop-access template](../assessment-batch-stop-access.json) as
`JumpServeTrainingBatchStopAccess`, using the current `CoordinatorInstance`
output. The stop document validates the batch ID and sends a graceful stop
to the matching systemd unit. Update the stop-access stack's instance
parameter if the coordinator moves to a new instance.

See [the coordinator template](../assessment-batch-coordinator.json) and the
[training batch setup](https://github.com/jumpserve-networks/jumpserve-front-end/blob/main/docs/synthetic-assessment-batch.md).
