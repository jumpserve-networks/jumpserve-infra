import * as cdk from 'aws-cdk-lib/core';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { PlatformSupervisorAccess } from '../lib/platform-supervisor-access';

test('platform releases use main-only OIDC and fixed service roles without static AWS credentials', () => {
  const stack = new cdk.Stack(new cdk.App(), 'PlatformTest', { env: { account: '395567831870', region: 'us-east-1' } });
  new PlatformSupervisorAccess(stack, 'Access', { workerRoleName: 'JumpServeOpenClawStack-WorkerRole-fixture', assetBucketName: 'cdk-hnb659fds-assets-395567831870-us-east-1', apiIds: ['d3o7xdethb'] });
  const template = Template.fromStack(stack);
  template.hasResourceProperties('AWS::IAM::Role', { RoleName: 'JumpServePlatformRelease', AssumeRolePolicyDocument: { Statement: [Match.objectLike({ Action: 'sts:AssumeRoleWithWebIdentity', Condition: { StringEquals: { 'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com', 'token.actions.githubusercontent.com:sub': 'repo:jumpserve-networks/jumpserve-infra:ref:refs/heads/main' } } })], Version: '2012-10-17' } });
  const raw = JSON.stringify(template.toJSON());
  for (const forbidden of ['AdministratorAccess', 'AWS_ACCESS_KEY_ID', 'ec2:RunInstances', 'iam:CreateRole', 'secretsmanager:PutSecretValue']) expect(raw).not.toContain(forbidden);
  template.hasResourceProperties('AWS::IAM::Policy', { PolicyDocument: { Statement: Match.arrayWith([Match.objectLike({ Action: 'iam:PassRole', Condition: { StringEquals: { 'iam:PassedToService': 'cloudformation.amazonaws.com' } } })]) } });
});

test('platform access synthesis requires discovered fixed-target values', () => {
  const stack = new cdk.Stack(new cdk.App(), 'InvalidPlatform', { env: { account: '395567831870', region: 'us-east-1' } });
  expect(() => new PlatformSupervisorAccess(stack, 'Access', { workerRoleName: 'Administrator', assetBucketName: 'arbitrary', apiIds: [] })).toThrow('Discover');
});
