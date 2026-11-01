import * as cdk from 'aws-cdk-lib';
import {Match, Template} from 'aws-cdk-lib/assertions';
import {PersistenceMonitor} from '../lib/persistence-monitor';

test('independent probe has bounded reads, least privilege and outage incidents even if telemetry stops', () => {
  const stack = new cdk.Stack(new cdk.App(), 'Monitoring', {env: {account: '395567831870', region: 'us-east-1'}});
  new PersistenceMonitor(stack, 'Persistence');
  const template = Template.fromStack(stack);
  template.hasResourceProperties('AWS::Lambda::Function', {
    Handler: 'monitor.handler', Runtime: 'python3.12', Timeout: 20,
    MemorySize: 128, ReservedConcurrentExecutions: 1,
    Environment: {Variables: {SUPABASE_SECRET_ARN: Match.anyValue()}},
  });
  template.hasResourceProperties('AWS::Events::Rule', {
    ScheduleExpression: 'rate(1 minute)',
    Targets: [Match.objectLike({RetryPolicy: {MaximumEventAgeInSeconds: 60, MaximumRetryAttempts: 0}})],
  });
  template.hasResourceProperties('AWS::CloudWatch::Alarm', {
    AlarmName: 'JumpServe-Supabase-Unavailable', Namespace: 'JumpServe/Persistence',
    MetricName: 'DatabaseReachable', Period: 60, Statistic: 'Minimum', Threshold: 1,
    EvaluationPeriods: 3, DatapointsToAlarm: 3, TreatMissingData: 'breaching',
    AlarmActions: [Match.anyValue()],
  });
  template.hasResourceProperties('AWS::CloudWatch::Alarm', {
    AlarmName: 'JumpServe-Supabase-Slow', Threshold: 2000,
    EvaluationPeriods: 5, DatapointsToAlarm: 3,
  });
  template.resourceCountIs('AWS::CloudWatch::Dashboard', 1);
  template.resourceCountIs('AWS::EC2::Instance', 0);
  const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'));
  for (const role of Object.values(template.findResources('AWS::IAM::Role'))) {
    expect(role.Properties.ManagedPolicyArns ?? []).toEqual([]);
  }
  expect(policies).toContain('logs:PutLogEvents');
  expect(policies).toContain('secretsmanager:GetSecretValue');
  expect(policies).toContain('jumpserve/supabase-service-key');
  expect(policies).toContain('cloudwatch:PutMetricData');
  expect(policies).toContain('cloudwatch:namespace');
  expect(policies).toContain('JumpServe/Persistence');
  for (const forbidden of ['ssm:SendCommand', 'lambda:InvokeFunction', 'bedrock:', 'ec2:', 'supabase-access-token', 'platform-supervisor']) {
    expect(policies).not.toContain(forbidden);
  }
  const alarms = JSON.stringify(template.findResources('AWS::CloudWatch::Alarm'));
  expect(alarms).toContain(':opsitem:1#CATEGORY=Availability');
  expect(alarms).toContain(':opsitem:3#CATEGORY=Performance');
});

test('monitor cannot be synthesized for another project account or region', () => {
  const stack = new cdk.Stack(new cdk.App(), 'WrongAccount', {env: {account: '111111111111', region: 'us-east-1'}});
  expect(() => new PersistenceMonitor(stack, 'Persistence')).toThrow('Fixed JumpServe');
});
