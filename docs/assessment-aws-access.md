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

The client role provisions and observes prefixed stacks and schedules.
Its CloudFormation delete permission requires the experiment ownership tag.
The expiration role can only request deletion of prefixed and tagged stacks.
CloudFormation uses its assigned execution role to remove the resources.
Keep the role policy available until all experiment stacks are gone.

Configure an AWS CLI profile using the approved source profile. For example,
when the existing `jumpserve` profile resolves to the approved principal, use
this in the local AWS CLI configuration.

```ini
[profile jumpserve-experiment]
role_arn = arn:aws:iam::395567831870:role/JumpServeExperimentClient
source_profile = jumpserve
```

Confirm the resulting account and role with
`aws sts get-caller-identity --profile jumpserve-experiment`.
EventBridge Scheduler and CloudFormation must be available in every selected
Region. The scheduled deadline requests a standard stack delete, so
deletion protection and dependencies that prevent deletion must be addressed
in the experiment design.
