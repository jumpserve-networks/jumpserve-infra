import * as cdk from 'aws-cdk-lib';
import * as api from 'aws-cdk-lib/aws-apigatewayv2';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as secrets from 'aws-cdk-lib/aws-secretsmanager';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import {Template, Match} from 'aws-cdk-lib/assertions';
import {createHash} from 'node:crypto';
import * as path from 'node:path';
import {OpenClawWorker} from '../lib/openclaw-worker';
import {IntakeWorker} from '../lib/intake-worker';
import {ResearchWorkflow, requireBuiltPackagePolicy, requireRepairQualification} from '../lib/research-workflow';
import {PlatformSupervisorAccess} from '../lib/platform-supervisor-access';
import {RealWorldTests} from '../lib/real-world-tests';

const fs = require('fs') as typeof import('fs');
const root = path.resolve(__dirname, '..');
const env = {account: '395567831870', region: 'us-east-1'};
afterEach(() => jest.restoreAllMocks());

function alterJSON(files: string[], mutate: (value: any) => void) {
  const original = fs.readFileSync;
  const replacements = new Map(files.map(file => {
    const filename = path.resolve(root, file), value = JSON.parse(original(filename, 'utf8'));
    mutate(value); return [filename, JSON.stringify(value)];
  }));
  jest.spyOn(fs, 'readFileSync').mockImplementation(((filename: any, options: any) => {
    const value = replacements.get(String(filename));
    return value === undefined ? original(filename, options) : options ? value : Buffer.from(value);
  }) as typeof fs.readFileSync);
}
function worker(kind: 'intake' | 'openclaw', target = env) {
  const stack = new cdk.Stack(new cdk.App(), 'PinCheck', {env: target});
  const vpc = new ec2.Vpc(stack, 'Vpc', {natGateways: 0, maxAzs: 1});
  const secret = secrets.Secret.fromSecretNameV2(stack, 'Key', 'jumpserve/supabase-service-key');
  if (kind === 'intake') return new IntakeWorker(stack, 'Worker', {vpc, secret, ownerRoleArn: 'arn:aws:iam::395567831870:role/JumpServeOpenClawStack-Worker-fixture'});
  return new OpenClawWorker(stack, 'Worker', {vpc, secret, runtime: path.join(root, '.runtime-backend/research_workflow')});
}
function research(context: Record<string, unknown> = {}, target = env, withExecutors = false) {
  const stack = new cdk.Stack(new cdk.App({context: {supabaseUrl: 'https://regphejnlvfpyokpniny.supabase.co', ...context}}), 'ResearchPin', {env: target});
  const executors = withExecutors ? {
    vpc: new ec2.Vpc(stack, 'Vpc', {natGateways: 0, maxAzs: 1}),
    emulated: new lambda.Function(stack, 'Emulated', {runtime: lambda.Runtime.NODEJS_22_X, handler: 'index.handler', code: lambda.Code.fromInline('exports.handler=async()=>({});')}),
    realWorld: new lambda.Function(stack, 'RealWorld', {runtime: lambda.Runtime.PYTHON_3_12, handler: 'index.handler', code: lambda.Code.fromInline('def handler(event,context): return {}')}),
  } : undefined;
  new ResearchWorkflow(stack, 'Research', new api.HttpApi(stack, 'Api'), executors);
  return Template.fromStack(stack);
}

test.each(['intake', 'openclaw'] as const)('%s refuses an unexpected AWS account', kind => {
  expect(() => worker(kind, {...env, account: '111111111111'})).toThrow(kind === 'intake' ? 'Verified existing refresh owner' : 'verified JumpServe account');
});

test.each([
  [{worker_ami_id: 'latest'}, 'Pinned worker AMI'],
  [{bootstrap_runtime_object: 'latest.zip'}, 'Retain the original bootstrap'],
  [{files: {'../escape': '0'.repeat(64)}}, 'Pinned OpenClaw worker inputs differ'],
])('OpenClaw rejects unpinned bootstrap inputs: %j', (change, message) => {
  alterJSON(['openclaw-worker-runtime.json'], value => Object.assign(value, change));
  expect(() => worker('openclaw')).toThrow(message);
});

test('OpenClaw rejects a changed controller hash before packaging assets', () => {
  alterJSON(['research-workflow-runtime.json'], value => {value.files[Object.keys(value.files)[0]] = '0'.repeat(64);});
  expect(() => worker('openclaw')).toThrow('OpenClaw controller bytes differ');
});

test('intake rejects an unqualified runtime manifest', () => {
  alterJSON(['.runtime-intake/intake-manifest.json'], value => {value.version = 'unqualified';});
  expect(() => worker('intake')).toThrow('Qualified pinned intake runtime required');
});

test('intake rejects unsafe source paths even when both manifests agree', () => {
  alterJSON(['.runtime-intake/intake-manifest.json', 'intake-worker-runtime.json'], value => {value.files = {'../escape': '0'.repeat(64)};});
  expect(() => worker('intake')).toThrow('Intake runtime source changed');
});

test('intake verifies native dependency bytes and its PDF requirement', () => {
  alterJSON(['openclaw-worker-runtime.json'], value => {value.files[Object.keys(value.files)[0]] = '0'.repeat(64);});
  expect(() => worker('intake')).toThrow('Pinned native dependencies differ');
  jest.restoreAllMocks();
  alterJSON(['autonomy-pdf-runtime.json'], value => {value.requirement = 'pypdf==0.0.0';});
  expect(() => worker('intake')).toThrow('Pinned intake PDF wheel differs');
});

test.each([{account: '111111111111', region: 'us-east-1'}, {account: env.account, region: 'us-west-2'}])('platform access refuses a different AWS target: %j', target => {
  const stack = new cdk.Stack(new cdk.App(), 'WrongTarget', {env: target});
  expect(() => new PlatformSupervisorAccess(stack, 'Access', {workerRoleName: '', assetBucketName: '', apiIds: []})).toThrow('Fixed JumpServe AWS target');
});

test('real-world deployment requires its prepared controller', () => {
  const original = fs.existsSync;
  jest.spyOn(fs, 'existsSync').mockImplementation(filename => String(filename).endsWith('/real_world/controller.py') ? false : original(filename));
  const stack = new cdk.Stack(new cdk.App(), 'MissingController');
  expect(() => new RealWorldTests(stack, 'RealWorld', new api.HttpApi(stack, 'Api'))).toThrow('Fetch the pinned backend runtime');
});

test('research rejects wrong account, database and OpenClaw-without-autonomy configurations', () => {
  expect(() => research({}, {...env, account: '111111111111'})).toThrow('requires AWS account');
  expect(() => research({supabaseUrl: 'https://other.test'})).toThrow('verified JumpServe Supabase project');
  expect(() => research({researchOpenClawEnabled: true})).toThrow('OpenClaw requires autonomous assessments');
  expect(() => research({researchAutonomyRepairEnabled: true})).toThrow('Autonomous repair requires');
});

test.each([
  ['research-workflow-runtime.json', 'Research runtime is absent'],
  ['research-api-runtime.json', 'Research API runtime differs'],
])('research rejects a manifest hash mismatch: %s', (manifest, message) => {
  alterJSON([manifest], value => {value.files[Object.keys(value.files)[0]] = '0'.repeat(64);});
  expect(() => research()).toThrow(message);
});

test('unknown built-package policy versions and absent qualification evidence fail closed', () => {
  expect(() => requireBuiltPackagePolicy({version: 'unrecognized'})).toThrow('Built package reservation differs');
  expect(() => requireRepairQualification({version: 'autonomous-repair-release-v1', approved_for_lab_recovery: true, qualified_files_sha256: '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'}, {})).toThrow('Passing exact-source live repair qualification');
});

test('autonomy rejects a cost policy that differs from its enforced resources', () => {
  const policyPath = 'policies/autonomy-experiment-costs-v2.json';
  const policy = JSON.parse(fs.readFileSync(path.join(root, '.runtime-backend/research_workflow', policyPath), 'utf8'));
  policy.bounded_tcp.memory_mb = 256;
  const sha = createHash('sha256').update(JSON.stringify(policy)).digest('hex');
  // A self-consistent synthetic manifest still cannot override enforced resources.
  alterJSON(['.runtime-backend/research_workflow/' + policyPath, 'research-workflow-runtime.json'], value => {
    if (value.bounded_tcp) value.bounded_tcp.memory_mb = 256; else value.files[policyPath] = sha;
  });
  expect(() => research({researchQueueEnabled: true, researchAutonomyEnabled: true})).toThrow('Bounded networking cost policy differs');
});

test('qualified repair activates its flag with shared-pool concurrency and registered executors', () => {
  const template = research({researchQueueEnabled: true, researchAutonomyEnabled: true, researchOpenClawEnabled: true,
    researchExperimentBuilderEnabled: true, researchAutonomyRepairEnabled: true, networkExecutionEnabled: true,
    researchReservedConcurrencyEnabled: 'false'}, env, true);
  template.hasResourceProperties('AWS::Lambda::Function', {Handler: 'autonomy.handler', Environment: {Variables: Match.objectLike({RESEARCH_AUTONOMY_REPAIR_ENABLED: 'true'})}});
  for (const resource of Object.values(template.findResources('AWS::Lambda::Function'))) expect(resource.Properties).not.toHaveProperty('ReservedConcurrentExecutions');
});

test('networking refuses an unpinned executor AMI', () => {
  expect(() => research({networkExecutionEnabled: true, networkPackageAmiId: 'latest'}, env, true)).toThrow('pinned package-experiment AMI');
});

test('autonomy verifies both the PDF layer identity and original file bytes', () => {
  alterJSON(['.runtime-autonomy-python/manifest.json'], value => {value.sha256 = '0'.repeat(64);});
  expect(() => research({researchQueueEnabled: true, researchAutonomyEnabled: true})).toThrow('Autonomous PDF dependency identity differs');
  jest.restoreAllMocks();
  const lock = JSON.parse(fs.readFileSync(path.join(root, 'autonomy-pdf-runtime.json'), 'utf8'));
  const first = path.join(root, '.runtime-autonomy-python/python', Object.keys(lock.files)[0]);
  const original = fs.readFileSync;
  jest.spyOn(fs, 'readFileSync').mockImplementation(((filename: any, options: any) => String(filename) === first ? Buffer.from('synthetic tampering') : original(filename, options)) as typeof fs.readFileSync);
  expect(() => research({researchQueueEnabled: true, researchAutonomyEnabled: true})).toThrow('Autonomous PDF dependency bytes differ');
});

test('undeclared PDF layer files are rejected before packaging', () => {
  const original = fs.readdirSync;
  const directory = path.join(root, '.runtime-autonomy-python');
  jest.spyOn(fs, 'readdirSync').mockImplementation(((filename: any, options: any) => {
    const entries = original(filename, options);
    return String(filename) === directory ? [...entries, {name: 'unreviewed.py', isDirectory: () => false}] : entries;
  }) as typeof fs.readdirSync);
  expect(() => research({researchQueueEnabled: true, researchAutonomyEnabled: true})).toThrow('Undeclared PDF layer files');
});
