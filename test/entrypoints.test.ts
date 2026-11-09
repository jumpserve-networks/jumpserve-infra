import * as path from 'node:path';

// Exercise entrypoint wiring without synthesis, asset bundling, lookups or AWS.
function load(entry: string, context: Record<string, unknown> = {}) {
  const app = {node: {tryGetContext: jest.fn((key: string) => context[key])}};
  const stack = {node: app.node};
  const App = jest.fn(() => app);
  const Stack = jest.fn(() => stack);
  const constructors: Record<string, jest.Mock> = {};
  const modules: Record<string, string> = {
    'amplify-stack': 'AmplifyStack', 'agent-stack': 'AgentStack',
    'benchmark-orchestrator-stack': 'BenchmarkOrchestratorStack',
    'intake-worker': 'IntakeWorker', 'openclaw-worker': 'OpenClawWorker',
    'platform-supervisor-access': 'PlatformSupervisorAccess', 'persistence-monitor': 'PersistenceMonitor',
  };
  const vpc = {id: 'synthetic-vpc'};
  const secret = {id: 'synthetic-secret'};
  const lookup = jest.fn(() => vpc);
  const secretLookup = jest.fn(() => secret);
  jest.isolateModules(() => {
    jest.doMock('aws-cdk-lib/core', () => ({App, Stack}));
    jest.doMock('aws-cdk-lib', () => ({App, Stack}));
    jest.doMock('aws-cdk-lib/aws-ec2', () => ({Vpc: {fromLookup: lookup}}));
    jest.doMock('aws-cdk-lib/aws-secretsmanager', () => ({Secret: {fromSecretNameV2: secretLookup}}));
    for (const [file, name] of Object.entries(modules)) {
      constructors[name] = jest.fn();
      jest.doMock(`../lib/${file}`, () => ({[name]: constructors[name]}));
    }
    require(`../bin/${entry}`);
  });
  return {app, stack, App, Stack, constructors, vpc, secret, lookup, secretLookup};
}

const env = {account: '395567831870', region: 'us-east-1'};

test.each([
  ['agent', 'AgentStack', 'JumpServeAgentStack'],
  ['benchmark', 'BenchmarkOrchestratorStack', 'JumpServeBenchmarkStack'],
])('%s release instantiates only its own stack', (entry, name, id) => {
  const result = load(entry);
  expect(result.App).toHaveBeenCalledTimes(1);
  expect(result.constructors[name]).toHaveBeenCalledWith(result.app, id, {env});
  expect(Object.values(result.constructors).reduce((n, mock) => n + mock.mock.calls.length, 0)).toBe(1);
});

test('combined app wires the three production stacks to the same environment', () => {
  const result = load('jumpserve-infra');
  for (const [name, id] of [['AmplifyStack', 'JumpServeAmplifyStack'], ['BenchmarkOrchestratorStack', 'JumpServeBenchmarkStack'], ['AgentStack', 'JumpServeAgentStack']]) {
    expect(result.constructors[name]).toHaveBeenCalledWith(result.app, id, {env});
  }
});

test('OpenClaw refuses an unverified database before looking up privileged resources', () => {
  expect(() => load('openclaw')).toThrow('Verified JumpServe project required.');
  expect(() => load('openclaw', {supabaseUrl: 'https://other.supabase.co'})).toThrow('Verified JumpServe project required.');
});

test('OpenClaw gets the runtime, VPC and service secret from the intended environment', () => {
  const result = load('openclaw', {supabaseUrl: 'https://regphejnlvfpyokpniny.supabase.co'});
  expect(result.Stack).toHaveBeenCalledWith(result.app, 'JumpServeOpenClawStack', {env});
  expect(result.lookup).toHaveBeenCalledWith(result.stack, 'DefaultVpc', {isDefault: true});
  expect(result.secretLookup).toHaveBeenCalledWith(result.stack, 'SupabaseServiceKey', 'jumpserve/supabase-service-key');
  expect(result.constructors.OpenClawWorker).toHaveBeenCalledWith(result.stack, 'Worker', {
    vpc: result.vpc, secret: result.secret,
    runtime: path.resolve(__dirname, '../.runtime-backend/research_workflow'),
  });
});

test('intake uses the dedicated stack with the existing worker role and shared secret', () => {
  const result = load('intake');
  expect(result.Stack).toHaveBeenCalledWith(result.app, 'JumpServeIntakeStack', {env});
  expect(result.lookup).toHaveBeenCalledWith(result.stack, 'DefaultVpc', {isDefault: true});
  expect(result.secretLookup).toHaveBeenCalledWith(result.stack, 'SupabaseServiceKey', 'jumpserve/supabase-service-key');
  expect(result.constructors.IntakeWorker).toHaveBeenCalledWith(result.stack, 'Intake', {
    vpc: result.vpc, secret: result.secret,
    ownerRoleArn: 'arn:aws:iam::395567831870:role/JumpServeOpenClawStack-WorkerRoleAAEB1603-AMhySy8UAI7S',
  });
});

test.each([
  [{}, {workerRoleName: '', assetBucketName: '', apiIds: []}],
  [{platformWorkerRoleName: 'worker', platformAssetBucketName: 'assets', platformApiIds: 'first,,second,'},
    {workerRoleName: 'worker', assetBucketName: 'assets', apiIds: ['first', 'second']}],
])('platform access forwards only configured identities and nonempty API ids', (context, props) => {
  const result = load('platform', context);
  expect(result.Stack).toHaveBeenCalledWith(result.app, 'JumpServePlatformAccessStack', {env});
  expect(result.constructors.PlatformSupervisorAccess).toHaveBeenCalledWith(result.stack, 'Access', props);
});

test('observability has its own stack and monitor', () => {
  const result = load('observability');
  expect(result.Stack).toHaveBeenCalledWith(result.app, 'JumpServeObservabilityStack', {env});
  expect(result.constructors.PersistenceMonitor).toHaveBeenCalledWith(result.stack, 'Persistence');
});
