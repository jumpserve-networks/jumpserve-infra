import * as cdk from 'aws-cdk-lib';
import * as api from 'aws-cdk-lib/aws-apigatewayv2';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { ResearchWorkflow, researchWorkflowIsEnabled } from '../lib/research-workflow';
test('explicit shared-pool production mode omits reservations while retaining bounded workers', () => {
  const app = new cdk.App({ context: { supabaseUrl: 'https://regphejnlvfpyokpniny.supabase.co', researchQueueEnabled: true, researchReservedConcurrencyEnabled: false } });
  const stack = new cdk.Stack(app, 'ResearchSharedPool', { env: { account: '395567831870', region: 'us-east-1' } });
  new ResearchWorkflow(stack, 'Research', new api.HttpApi(stack, 'Api'));
  const template = Template.fromStack(stack);
  for (const resource of Object.values(template.findResources('AWS::Lambda::Function'))) expect(resource.Properties).not.toHaveProperty('ReservedConcurrentExecutions');
  template.hasResourceProperties('AWS::Lambda::Function', { Handler: 'worker.handler', MemorySize: 512, Timeout: 180 });
  template.hasResourceProperties('AWS::Events::Rule', { ScheduleExpression: 'rate(1 minute)' });
});
test.each([[true,true],['true',true],[false,false],['false',false],[undefined,false],['1',false],[1,false]])('CDK context %s explicitly enables research only as declared', (value, expected) => {
  expect(researchWorkflowIsEnabled(value)).toBe(expected);
});
test('research API has bounded resources, explicit routes and no experiment or model permissions', () => {
  const app = new cdk.App({ context: { supabaseUrl: 'https://regphejnlvfpyokpniny.supabase.co', supabaseAnonKey: 'public-test-key' } });
  const stack = new cdk.Stack(app, 'ResearchTest', { env: { account: '395567831870', region: 'us-east-1' } });
  new ResearchWorkflow(stack, 'Research', new api.HttpApi(stack, 'Api'));
  const template = Template.fromStack(stack);
  template.resourceCountIs('AWS::Lambda::Function', 1);
  template.hasResourceProperties('AWS::Lambda::Function', { Handler: 'api.handler', Timeout: 29, MemorySize: 512, ReservedConcurrentExecutions: 4, Environment: { Variables: Match.objectLike({ SUPABASE_URL: 'https://regphejnlvfpyokpniny.supabase.co' }) } });
  for (const endpoint of ['records', 'protocols', 'runs', 'publish', 'queue', 'queue-actions', 'prepare']) template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: `POST /research/studies/{studyId}/${endpoint}` });
  template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: 'GET /research/studies/{studyId}/prepare' });
  template.resourceCountIs('AWS::Events::Rule', 0);
  const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'));
  expect(policies).toContain('secretsmanager:GetSecretValue');
  for (const action of ['ec2:', 'bedrock:', 'states:', 'ssm:', 's3:']) expect(policies).not.toContain(action);
});
test('explicit queue flag provisions two bounded workers and one-minute poll without experiment permissions', () => {
  const app = new cdk.App({ context: { supabaseUrl: 'https://regphejnlvfpyokpniny.supabase.co', researchQueueEnabled: 'true' } });
  const stack = new cdk.Stack(app, 'ResearchQueueTest', { env: { account: '395567831870', region: 'us-east-1' } });
  new ResearchWorkflow(stack, 'Research', new api.HttpApi(stack, 'Api'));
  const template = Template.fromStack(stack);
  template.resourceCountIs('AWS::Lambda::Function', 2);
  template.hasResourceProperties('AWS::Lambda::Function', { Handler: 'worker.handler', Timeout: 180, MemorySize: 512, ReservedConcurrentExecutions: 2 });
  template.hasResourceProperties('AWS::Events::Rule', { ScheduleExpression: 'rate(1 minute)', Targets: Match.arrayWith([Match.objectLike({ RetryPolicy: { MaximumEventAgeInSeconds: 60, MaximumRetryAttempts: 0 } })]) });
  template.hasResourceProperties('AWS::Lambda::EventInvokeConfig', { MaximumRetryAttempts: 0, MaximumEventAgeInSeconds: 60 });
  const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'));
  for (const action of ['ec2:', 'bedrock:', 'states:', 'ssm:', 's3:']) expect(policies).not.toContain(action);
});
