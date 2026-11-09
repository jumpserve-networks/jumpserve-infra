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
    const groupRef = template.toJSON().Outputs.BenchmarkSecurityGroupId.Value.Ref;
    expect(typeof groupRef).toBe('string');
    expect(template.toJSON().Resources[groupRef].Type).toBe('AWS::EC2::SecurityGroup');
    expect(template.toJSON().Resources[groupRef].Properties.VpcId).toBeDefined();
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
    const profileId = Object.keys(template.findResources('AWS::IAM::InstanceProfile'))[0];
    const launcher = Object.values(template.findResources('AWS::Lambda::Function')).find(
      (resource: any) => resource.Properties.Environment?.Variables?.BENCHMARK_IMAGE_MODE,
    );
    expect(launcher).toBeDefined();
    const profileArn = launcher.Properties.Environment.Variables.INSTANCE_PROFILE_ARN;
    expect(profileArn).toEqual({ 'Fn::Join': ['', [
      'arn:', { Ref: 'AWS::Partition' }, ':iam::395567831870:instance-profile/', { Ref: profileId },
    ]] });
    expect(JSON.stringify(profileArn)).not.toContain('Fn::GetAtt');
  } finally {
    lookup.mockRestore();
  }
});

test('an explicitly enabled research workflow is mounted on the benchmark API', () => {
  const app = new cdk.App({context: {supabaseUrl: 'https://regphejnlvfpyokpniny.supabase.co', researchWorkflowEnabled: true}});
  const lookup = jest.spyOn(ec2.Vpc, 'fromLookup').mockImplementation((scope, id) => ec2.Vpc.fromVpcAttributes(scope, id, {
    vpcId: 'vpc-unit', availabilityZones: ['us-east-1a'], publicSubnetIds: ['subnet-unit'], publicSubnetRouteTableIds: ['rtb-unit'],
  }));
  try {
    const template = Template.fromStack(new BenchmarkOrchestratorStack(app, 'WithResearch', {env: {account: '395567831870', region: 'us-east-1'}}));
    template.hasResourceProperties('AWS::ApiGatewayV2::Route', {RouteKey: 'GET /research/papers'});
    template.hasResourceProperties('AWS::ApiGatewayV2::Route', {RouteKey: 'POST /benchmarks'});
  } finally {lookup.mockRestore();}
});
