import * as cdk from 'aws-cdk-lib/core';
import { Template } from 'aws-cdk-lib/assertions';
import { PlatformSupervisorAccess } from '../lib/platform-supervisor-access';

test('self-install powers belong to the OIDC release role and target one existing host', () => {
  const stack = new cdk.Stack(new cdk.App(), 'SupervisorSelfAccess', { env: { account: '395567831870', region: 'us-east-1' } });
  new PlatformSupervisorAccess(stack, 'Access', { workerRoleName: 'JumpServeOpenClawStack-WorkerRole-fixture', assetBucketName: 'cdk-hnb659fds-assets-395567831870-us-east-1', apiIds: ['d3o7xdethb'] });
  const template = Template.fromStack(stack);
  const roles = template.findResources('AWS::IAM::Role');
  const release = Object.keys(roles).find(key => roles[key].Properties.RoleName === 'JumpServePlatformRelease');
  expect(release).toBeDefined();
  const policies = Object.values(template.findResources('AWS::IAM::Policy'));
  const selfPolicy = policies.find(policy => policy.Properties.PolicyDocument.Statement.some((statement: { Action: string | string[] }) => [statement.Action].flat().includes('ssm:SendCommand')));
  expect(selfPolicy).toBeDefined();
  expect(selfPolicy!.Properties.Roles).toEqual([{ Ref: release }]);
  const statements = selfPolicy!.Properties.PolicyDocument.Statement;
  const install = statements.find((statement: { Action: string | string[] }) => [statement.Action].flat().includes('ssm:SendCommand'));
  expect(install.Resource).toEqual([
    'arn:aws:ssm:us-east-1::document/AWS-RunShellScript',
    'arn:aws:ec2:us-east-1:395567831870:instance/i-087f1493809643115',
  ]);
  const readKey = statements.find((statement: { Action: string | string[] }) => [statement.Action].flat().includes('secretsmanager:GetSecretValue'));
  expect(readKey.Resource).toBe('arn:aws:secretsmanager:us-east-1:395567831870:secret:jumpserve/supabase-service-key-*');
});
