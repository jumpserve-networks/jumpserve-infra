import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { BenchmarkOrchestratorStack } from '../lib/benchmark-orchestrator-stack';

test('the selected AMI and bootstrap mode always change together', () => {
  const app = new cdk.App({ context: { supabaseUrl: 'https://example.supabase.co' } });
  const lookup = jest.spyOn(ec2.Vpc, 'fromLookup').mockImplementation((scope, id) => (
    ec2.Vpc.fromVpcAttributes(scope, id, {
      vpcId: 'vpc-test', availabilityZones: ['us-east-1a'],
      publicSubnetIds: ['subnet-test'], publicSubnetRouteTableIds: ['rtb-test'],
    })
  ));
  try {
    const stack = new BenchmarkOrchestratorStack(app, 'TestBenchmarkStack', {
      env: { account: '395567831870', region: 'us-east-1' },
    });
    const template = Template.fromStack(stack);
  template.resourceCountIs('AWS::Lambda::Url', 0);
    const policies = template.findResources('AWS::IAM::Policy');
    const instancePolicies = Object.values(policies).filter((policy: any) =>
      JSON.stringify(policy.Properties.Roles).includes('BenchmarkInstanceRole'));
    const statements = instancePolicies.flatMap((policy: any) => policy.Properties.PolicyDocument.Statement);
    expect(statements.some((statement: any) => statement.Effect === 'Deny' &&
      statement.Action.includes('secretsmanager:GetSecretValue'))).toBe(true);
    expect(statements.some((statement: any) => statement.Effect === 'Allow' &&
      JSON.stringify(statement.Action).includes('secretsmanager:'))).toBe(false);
    template.hasResourceProperties('AWS::ApiGatewayV2::Route', { RouteKey: 'POST /benchmarks/ingest' });
    template.hasParameter('BenchmarkAmiId', { Type: 'String', Default: '' });
    template.hasCondition('UseBenchmarkAmi', {
      'Fn::Not': [{ 'Fn::Equals': [{ Ref: 'BenchmarkAmiId' }, ''] }],
    });
    template.hasResourceProperties('AWS::Lambda::Function', {
      Environment: { Variables: Match.objectLike({
        AMI_ID: { 'Fn::If': ['UseBenchmarkAmi', { Ref: 'BenchmarkAmiId' }, Match.anyValue()] },
        BENCHMARK_IMAGE_MODE: { 'Fn::If': ['UseBenchmarkAmi', 'prebaked', 'base'] },
      }) },
    });
  } finally {
    lookup.mockRestore();
  }
});
