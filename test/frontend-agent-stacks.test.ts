import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import {Template, Match} from 'aws-cdk-lib/assertions';
import {mkdtempSync, writeFileSync, rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import * as path from 'node:path';
import {AmplifyStack} from '../lib/amplify-stack';
import {AgentStack} from '../lib/agent-stack';

const env = {account: '395567831870', region: 'us-east-1'};
const database = {supabaseUrl: 'https://database.example.test', supabaseAnonKey: 'synthetic-public-key', benchmarkApiUrl: 'https://api.example.test'};

test.each([false, true])('frontend stack synthesizes configured and default repository/domain settings: custom=%s', custom => {
  const context = {...database, ...(custom ? {frontendRepo: 'example/frontend', customDomain: 'app.example.test', agentUrl: 'https://agent.example.test'} : {benchmarkApiUrl: undefined})};
  const app = new cdk.App({context});
  const template = Template.fromStack(new AmplifyStack(app, 'Frontend', {env}));
  template.hasResourceProperties('AWS::Amplify::App', {
    Repository: `https://github.com/${custom ? 'example/frontend' : 'BradleyFang/jumpserve-front-end'}`,
    Platform: 'WEB_COMPUTE',
    EnvironmentVariables: Match.arrayWith([
      {Name: 'NEXT_PUBLIC_SUPABASE_URL', Value: database.supabaseUrl},
      {Name: 'NEXT_PUBLIC_SUPABASE_ANON_KEY', Value: database.supabaseAnonKey},
      {Name: 'NEXT_PUBLIC_BENCHMARK_API_URL', Value: custom ? database.benchmarkApiUrl : ''},
      {Name: 'NEXT_PUBLIC_AGENT_URL', Value: custom ? 'https://agent.example.test' : ''},
    ]),
  });
  template.hasResourceProperties('AWS::Amplify::Branch', {BranchName: 'main', Stage: 'PRODUCTION', EnableAutoBuild: true});
  template.resourceCountIs('AWS::Amplify::Domain', custom ? 1 : 0);
  if (custom) template.hasOutput('CustomDomainUrl', {Value: 'https://app.example.test'});
  const appResource = Object.values(template.findResources('AWS::Amplify::App'))[0];
  expect(JSON.parse(appResource.Properties.BuildSpec).frontend.phases).toEqual({preBuild: {commands: ['npm ci']}, build: {commands: ['npm run build']}});
  expect(JSON.stringify(template.toJSON())).toContain('jumpserve/github-token');
});

test.each([undefined, 'synthetic-public-key'])('agent uses an isolated Python layer, server secret and public-key fallback: %s', anonKey => {
  // A tiny local asset verifies CDK wiring without packaging installed/vendor code.
  const directory = mkdtempSync(path.join(tmpdir(), 'jumpserve-unit-agent-'));
  writeFileSync(path.join(directory, 'handler.py'), 'def lambda_handler(event, context): return {}\n');
  const original = lambda.Code.fromAsset;
  const asset = jest.spyOn(lambda.Code, 'fromAsset').mockImplementation(() => original(directory));
  try {
    const app = new cdk.App({context: {...database, supabaseAnonKey: anonKey}});
    const template = Template.fromStack(new AgentStack(app, 'Agent', {env}));
    template.hasResourceProperties('AWS::Lambda::Function', {
      Handler: 'handler.lambda_handler', Runtime: 'python3.12', MemorySize: 1024, Timeout: 120,
      Architectures: ['x86_64'],
      Environment: {Variables: Match.objectLike({SUPABASE_URL: database.supabaseUrl, SUPABASE_ANON_KEY: anonKey ?? '', BENCHMARK_API_URL: database.benchmarkApiUrl})},
    });
    template.hasResourceProperties('AWS::Lambda::LayerVersion', {CompatibleRuntimes: ['python3.12']});
    template.hasResourceProperties('AWS::Lambda::Url', {AuthType: 'NONE', Cors: {AllowOrigins: ['*'], AllowMethods: ['POST'], AllowHeaders: ['Content-Type', 'Authorization']}});
    const policies = JSON.stringify(template.findResources('AWS::IAM::Policy'));
    expect(policies).toContain('secretsmanager:GetSecretValue');
    expect(policies).toContain('bedrock:InvokeModel');
    expect(policies).not.toContain('secretsmanager:PutSecretValue');
    expect(asset.mock.calls).toHaveLength(2);
    expect(asset.mock.calls[1][1]?.exclude).toContain('package/*');
    template.hasOutput('AgentFunctionUrl', {Value: Match.anyValue()});
  } finally {asset.mockRestore(); rmSync(directory, {recursive: true, force: true});}
});
