import * as cdk from 'aws-cdk-lib/core';
import { Template } from 'aws-cdk-lib/assertions';
import { PlatformSupervisorAccess } from '../lib/platform-supervisor-access';

test('release role can distinguish an absent immutable service marker only in its fixed asset bucket', () => {
  const stack = new cdk.Stack(new cdk.App(), 'ServiceMarkerTest', { env: { account: '395567831870', region: 'us-east-1' } });
  new PlatformSupervisorAccess(stack, 'Access', { workerRoleName: 'JumpServeOpenClawStack-WorkerRole-fixture', assetBucketName: 'cdk-hnb659fds-assets-395567831870-us-east-1', apiIds: ['d3o7xdethb'] });
  const template = Template.fromStack(stack);
  const roles = template.findResources('AWS::IAM::Role');
  const release = Object.keys(roles).find(key => roles[key].Properties.RoleName === 'JumpServePlatformRelease');
  expect(release).toBeDefined();
  const policies = Object.values(template.findResources('AWS::IAM::Policy')).filter(policy => policy.Properties.Roles.some((role: { Ref?: string }) => role.Ref === release));
  const statements = policies.flatMap(policy => policy.Properties.PolicyDocument.Statement);
  const actions = (statement: { Action: string | string[] }): string[] => Array.isArray(statement.Action) ? statement.Action : [statement.Action];
  expect(statements.filter(statement => actions(statement).includes('s3:ListBucket'))).toEqual([
    { Effect: 'Allow', Action: 's3:ListBucket', Resource: 'arn:aws:s3:::cdk-hnb659fds-assets-395567831870-us-east-1' },
  ]);
  for (const forbidden of ['s3:*', 's3:ListAllMyBuckets', 's3:DeleteObject', 's3:PutBucketPolicy']) {
    expect(statements.some(statement => actions(statement).includes(forbidden))).toBe(false);
  }
});
