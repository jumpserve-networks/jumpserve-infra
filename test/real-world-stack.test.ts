import * as cdk from 'aws-cdk-lib';
import * as api from 'aws-cdk-lib/aws-apigatewayv2';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { RealWorldTests } from '../lib/real-world-tests';

test('real-world lifecycle retains evidence and independently reaps expired resources', () => {
  const app = new cdk.App({ context: { supabaseUrl: 'https://example.supabase.co', supabaseAnonKey: 'public-test-key' } });
  const stack = new cdk.Stack(app, 'RealWorldTest', { env: { account: '123456789012', region: 'us-east-1' } });
  new RealWorldTests(stack, 'RealWorld', new api.HttpApi(stack, 'Api'));
  const template = Template.fromStack(stack);
  template.resourceCountIs('AWS::StepFunctions::StateMachine', 1);
  template.hasResourceProperties('AWS::Events::Rule', { ScheduleExpression: 'rate(5 minutes)' });
  template.hasResourceProperties('AWS::Lambda::Function', { Handler: 'controller.reap', Timeout: 240 });
  template.hasResourceProperties('AWS::Lambda::Function', { Handler: 'api.handler', Environment: { Variables: Match.objectLike({ SUPABASE_URL: 'https://example.supabase.co' }) } });
  template.hasResource('AWS::S3::Bucket', { DeletionPolicy: 'RetainExceptOnCreate' });
  template.hasResource('AWS::DynamoDB::Table', { DeletionPolicy: 'RetainExceptOnCreate' });
  template.hasResourceProperties('AWS::DynamoDB::Table', { GlobalSecondaryIndexes: Match.arrayWith([Match.objectLike({ IndexName: 'active-deadline' })]) });
  template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: 'POST /real-world/tests/{jobId}/cancel' });
  for (const route of ['/real-world/reports', '/real-world/reports/{jobId}', '/real-world/reports/{jobId}/artifacts']) {
    template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: `GET ${route}` });
  }
  template.hasResourceProperties('AWS::DynamoDB::Table', { GlobalSecondaryIndexes: Match.arrayWith([Match.objectLike({ IndexName: 'reports-created', KeySchema: [
    { AttributeName: 'schema_version', KeyType: 'HASH' }, { AttributeName: 'created_at', KeyType: 'RANGE' },
  ] })]) });
  const roles = template.findResources('AWS::IAM::Role');
  const instanceRole = Object.entries(roles).find(([name]) => name.includes('InstanceRole'))?.[1];
  expect(JSON.stringify(instanceRole)).not.toContain('secretsmanager');
  const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'));
  expect(policies).toContain('ec2:ResourceTag/Project');
  expect(policies).toContain('JumpServeRealWorld');
  const workerPolicy = Object.entries(template.findResources('AWS::IAM::Policy')).find(([name]) => name.includes('WorkerRole'))?.[1];
  if (!workerPolicy) throw new Error('Missing real-world worker policy');
  const launches = workerPolicy.Properties.PolicyDocument.Statement.filter((statement: { Action: string | string[] }) =>
    [statement.Action].flat().includes('ec2:RunInstances'));
  const instanceLaunches = launches.filter((statement: { Resource: unknown }) => JSON.stringify(statement.Resource).includes(':instance/*'));
  expect(instanceLaunches).toHaveLength(1);
  expect(instanceLaunches[0].Condition).toEqual({ StringEquals: { 'ec2:InstanceType': 't3.medium' } });
  expect(launches.every((statement: { Resource: unknown }) => statement.Resource !== '*')).toBe(true);
  for (const policy of Object.values(template.findResources('AWS::IAM::Policy'))) {
    for (const statement of policy.Properties.PolicyDocument.Statement) {
      expect([statement.Action].flat()).not.toContain('ec2:*');
    }
  }
});
