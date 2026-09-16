import * as cdk from 'aws-cdk-lib/core';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

/** Credentials for the backend main-branch AMI workflow, without static keys. */
export function addBenchmarkImagePipelineRole(
  scope: Construct,
  benchmarkInstanceRole: iam.IRole,
  launcherArn: string,
): iam.Role {
  const stack = cdk.Stack.of(scope);
  const arn = (service: string, resource: string, account = stack.account) =>
    `arn:${stack.partition}:${service}:${service === 'iam' ? '' : stack.region}:${account}:${resource}`;
  const provider = new iam.CfnOIDCProvider(scope, 'GitHubActionsOidc', {
    url: 'https://token.actions.githubusercontent.com',
    clientIdList: ['sts.amazonaws.com'],
  });
  const role = new iam.Role(scope, 'BenchmarkImagePipelineRole', {
    roleName: 'JumpServeBenchmarkImageBuilder',
    maxSessionDuration: cdk.Duration.hours(2),
    assumedBy: new iam.WebIdentityPrincipal(provider.attrArn, {
      StringEquals: {
        'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
        'token.actions.githubusercontent.com:sub': 'repo:jumpserve-networks/jumpserve-back-end:ref:refs/heads/main',
      },
    }),
  });
  const allow = (actions: string[], resources: string[], conditions?: Record<string, Record<string, unknown>>) =>
    role.addToPolicy(new iam.PolicyStatement({ actions, resources, conditions }));

  allow(['ec2:DescribeImages', 'ec2:DescribeInstances'], ['*']);
  allow(['ec2:RunInstances', 'ec2:CreateImage'], ['*'], {
    StringEquals: { 'aws:RequestedRegion': stack.region },
  });
  allow(['ec2:CreateTags'], [arn('ec2', '*'), arn('ec2', 'image/*', '')], {
    StringEquals: { 'ec2:CreateAction': ['RunInstances', 'CreateImage'] },
  });
  allow(['ec2:TerminateInstances'], [arn('ec2', 'instance/*')], {
    StringEquals: { 'ec2:ResourceTag/Project': 'JumpServe' },
  });

  const builderRoles = arn('iam', 'role/JumpServeAmiBuilder-*');
  const builderProfiles = arn('iam', 'instance-profile/JumpServeAmiBuilder-*');
  allow(['iam:CreateRole', 'iam:DeleteRole', 'iam:GetRole'], [builderRoles]);
  allow(['iam:CreateInstanceProfile', 'iam:DeleteInstanceProfile', 'iam:GetInstanceProfile',
    'iam:AddRoleToInstanceProfile', 'iam:RemoveRoleFromInstanceProfile'], [builderProfiles]);
  allow(['iam:AttachRolePolicy', 'iam:DetachRolePolicy'], [builderRoles], {
    ArnEquals: { 'iam:PolicyARN': 'arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore' },
  });
  allow(['iam:PassRole'], [builderRoles, benchmarkInstanceRole.roleArn], {
    StringEquals: { 'iam:PassedToService': 'ec2.amazonaws.com' },
  });

  allow(['ssm:DescribeInstanceInformation', 'ssm:ListCommandInvocations'], ['*']);
  allow(['ssm:SendCommand'], [arn('ssm', 'document/AWS-RunShellScript', '')]);
  allow(['ssm:SendCommand'], [arn('ec2', 'instance/*')], {
    StringEquals: { 'ssm:resourceTag/Project': 'JumpServe' },
  });
  allow(['ssm:GetParameter'], [arn('ssm',
    'parameter/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id', '')]);
  allow(['lambda:GetFunctionConfiguration'], [launcherArn]);
  allow(['logs:GetLogEvents'], [arn('logs', 'log-group:/jumpserve/benchmark:*')]);
  allow(['cloudformation:DescribeStacks', 'cloudformation:UpdateStack'], [arn('cloudformation', 'stack/JumpServeBenchmarkStack/*')]);
  allow(['iam:PassRole'], [arn('iam', `role/cdk-hnb659fds-cfn-exec-role-${stack.account}-${stack.region}`)], {
    StringEquals: { 'iam:PassedToService': 'cloudformation.amazonaws.com' },
  });
  new cdk.CfnOutput(scope, 'BenchmarkImagePipelineRoleArn', { value: role.roleArn });
  return role;
}
