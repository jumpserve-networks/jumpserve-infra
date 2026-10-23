import * as cdk from 'aws-cdk-lib';
import * as api from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import { Construct } from 'constructs';
import * as path from 'path';
import * as fs from 'fs';
import { createHash } from 'crypto';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';

export function researchWorkflowIsEnabled(value: unknown): boolean {
  return value === true || value === 'true';
}

export class ResearchWorkflow extends Construct {
  constructor(scope: Construct, id: string, httpApi: api.HttpApi, executors?: {emulated:lambda.IFunction;realWorld:lambda.IFunction;vpc:ec2.IVpc}) {
    super(scope, id);
    if (cdk.Stack.of(this).account !== '395567831870') throw new Error('Research workflow requires AWS account 395567831870.');
    const runtime = process.env.RESEARCH_WORKFLOW_RUNTIME_PATH ?? path.join(__dirname, '..', '.runtime-backend', 'research_workflow');
    const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'research-workflow-runtime.json'), 'utf8')) as { files: Record<string, string> };
    for (const [file, sha256] of Object.entries(manifest.files)) {
      if (!/^(?:[a-z_]+\.(?:py|mjs)|(?:plans|policies)\/[a-z0-9-]+\.json)$/.test(file) || !fs.existsSync(path.join(runtime, file)) || createHash('sha256').update(fs.readFileSync(path.join(runtime, file))).digest('hex') !== sha256) {
        throw new Error('Research runtime is absent or differs from the manifest. Run bin/prepare-research-runtime.py with the documented backend checkout.');
      }
    }
    const url = this.node.tryGetContext('supabaseUrl');
    if (url !== 'https://regphejnlvfpyokpniny.supabase.co') throw new Error('Research workflow requires the verified JumpServe Supabase project.');
    const secret = secretsmanager.Secret.fromSecretNameV2(this, 'SupabaseServiceKey', 'jumpserve/supabase-service-key');
    const queueEnabled = researchWorkflowIsEnabled(this.node.tryGetContext('researchQueueEnabled'));
    const autonomyEnabled = researchWorkflowIsEnabled(this.node.tryGetContext('researchAutonomyEnabled'));
    const openclawEnabled=researchWorkflowIsEnabled(this.node.tryGetContext('researchOpenClawEnabled'));
    if(openclawEnabled&&!autonomyEnabled)throw new Error('OpenClaw requires autonomous assessments.');
    const aiEnvironment:Record<string,string>=openclawEnabled?{RESEARCH_AI_RUNTIME:'openclaw-production-v1'}:{};
    const admissionContext = this.node.tryGetContext('researchAutonomyAdmissionEnabled');
    const autonomyAdmission = autonomyEnabled && (admissionContext === undefined || researchWorkflowIsEnabled(admissionContext));
    if (autonomyEnabled && !queueEnabled) throw new Error('Autonomous assessments require the durable experiment queue.');
    const reservationContext = this.node.tryGetContext('researchReservedConcurrencyEnabled');
    const reserveConcurrency = reservationContext !== false && reservationContext !== 'false';
    const networkingEnabled = Boolean(executors) && researchWorkflowIsEnabled(this.node.tryGetContext('networkExecutionEnabled'));
    const packagesEnabled = networkingEnabled && researchWorkflowIsEnabled(this.node.tryGetContext('networkPackagesEnabled'));
    const networkingEnvironment: Record<string,string> = {};
    let boundedVersion: lambda.IVersion | undefined;
    if (autonomyEnabled) {
      const policy = JSON.parse(fs.readFileSync(path.join(runtime, 'policies/autonomy-experiment-costs-v2.json'), 'utf8')).bounded_tcp;
      if (policy.runner !== 'bounded-tcp-v1' || policy.region !== cdk.Stack.of(this).region || policy.memory_mb !== 128 || policy.timeout_seconds !== 5 || policy.remote_network_bytes !== 0 || policy.ec2_instances !== 0 || policy.maximum_cents !== 1) throw new Error('Bounded networking cost policy differs from enforced infrastructure.');
      const role = new iam.Role(this, 'BoundedTcpRole', { assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com') });
      const logGroup = new logs.LogGroup(this, 'BoundedTcpLogs', { retention: logs.RetentionDays.ONE_DAY });
      logGroup.grantWrite(role);
      const bounded = new lambda.Function(this, 'BoundedTcp', {
        code: lambda.Code.fromInline(fs.readFileSync(path.join(runtime, 'bounded_network.py'), 'utf8')),
        handler: 'index.handler', runtime: lambda.Runtime.PYTHON_3_12, architecture: lambda.Architecture.X86_64,
        memorySize: 128, timeout: cdk.Duration.seconds(5), ephemeralStorageSize: cdk.Size.mebibytes(512),
        reservedConcurrentExecutions: reserveConcurrency ? 2 : undefined, retryAttempts: 0,
        role, logGroup, description: 'Immutable bounded TCP loopback exchanges; no remote targets, packages, EC2 or cloud API permissions.',
      });
      boundedVersion = bounded.currentVersion;
      networkingEnvironment.NETWORK_BOUNDED_FUNCTION = boundedVersion.functionArn;
      networkingEnvironment.NETWORK_BOUNDED_POLICY_SHA256 = createHash('sha256').update(JSON.stringify(policy, Object.keys(policy).sort())).digest('hex');
    }
    let packageExecutor: lambda.Function | undefined;
    if (networkingEnabled && executors) {
      const packageVpc = new ec2.Vpc(this,'PackageVpc',{maxAzs:1,natGateways:0,subnetConfiguration:[{name:'Experiment',subnetType:ec2.SubnetType.PUBLIC,cidrMask:24}]});
      const sg = new ec2.SecurityGroup(this,'PackageMachines',{vpc:packageVpc,description:'Isolated networking packages: no inbound access and no instance IAM profile',allowAllOutbound:true});
      const machineEnvironment = {SUPABASE_URL:url,SUPABASE_SECRET_ARN:secret.secretArn,NETWORK_AWS_ACCOUNT:'395567831870',
        NETWORK_PACKAGE_AMI:ec2.MachineImage.fromSsmParameter('/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id').getImage(this).imageId,
        NETWORK_PACKAGE_SUBNET:packageVpc.publicSubnets[0].subnetId,NETWORK_PACKAGE_SECURITY_GROUP:sg.securityGroupId,NETWORK_PACKAGE_INGEST_URL:`${httpApi.apiEndpoint}/research/network-ingest`};
      packageExecutor = new lambda.Function(this,'PackageExecutor',{code:lambda.Code.fromAsset(runtime),handler:'network_package.handler',runtime:lambda.Runtime.PYTHON_3_12,memorySize:512,timeout:cdk.Duration.seconds(60),retryAttempts:0,environment:machineEnvironment});
      const reaper = new lambda.Function(this,'PackageReaper',{code:lambda.Code.fromAsset(runtime),handler:'network_package.reap',runtime:lambda.Runtime.PYTHON_3_12,memorySize:256,timeout:cdk.Duration.seconds(120),retryAttempts:0,environment:machineEnvironment});
      for (const service of [packageExecutor,reaper]) {
        secret.grantRead(service);
        service.addToRolePolicy(new iam.PolicyStatement({actions:['ec2:DescribeInstances'],resources:['*']}));
        service.addToRolePolicy(new iam.PolicyStatement({actions:['ec2:TerminateInstances'],resources:[cdk.Stack.of(this).formatArn({service:'ec2',resource:'instance',resourceName:'*',arnFormat:cdk.ArnFormat.SLASH_RESOURCE_NAME})],conditions:{StringEquals:{'ec2:ResourceTag/Project':'JumpServeNetworkPackage'}}}));
      }
      packageExecutor.addToRolePolicy(new iam.PolicyStatement({actions:['ec2:RunInstances'],resources:[
        `arn:aws:ec2:${cdk.Stack.of(this).region}::image/*`,
        ...['subnet','security-group','network-interface','volume','instance'].map(resource=>cdk.Stack.of(this).formatArn({service:'ec2',resource,resourceName:'*',arnFormat:cdk.ArnFormat.SLASH_RESOURCE_NAME}))],conditions:{StringEquals:{'aws:RequestedRegion':cdk.Stack.of(this).region}}}));
      packageExecutor.addToRolePolicy(new iam.PolicyStatement({actions:['ec2:CreateTags'],resources:[cdk.Stack.of(this).formatArn({service:'ec2',resource:'instance',resourceName:'*',arnFormat:cdk.ArnFormat.SLASH_RESOURCE_NAME})],conditions:{StringEquals:{'ec2:CreateAction':'RunInstances','aws:RequestTag/Project':'JumpServeNetworkPackage'}}}));
      const ingest = new lambda.Function(this,'PackageIngest',{code:lambda.Code.fromAsset(runtime),handler:'network_package.ingest',runtime:lambda.Runtime.PYTHON_3_12,memorySize:512,timeout:cdk.Duration.seconds(29),environment:{SUPABASE_URL:url,SUPABASE_SECRET_ARN:secret.secretArn}});
      secret.grantRead(ingest);
      httpApi.addRoutes({path:'/research/network-ingest',methods:[api.HttpMethod.POST],integration:new HttpLambdaIntegration('PackageIngestIntegration',ingest)});
      new events.Rule(this,'PackageDeadlineCleanup',{schedule:events.Schedule.rate(cdk.Duration.minutes(1)),targets:[new targets.LambdaFunction(reaper,{retryAttempts:0})]});
      networkingEnvironment.NETWORK_EMULATED_FUNCTION=executors.emulated.functionArn;
      networkingEnvironment.NETWORK_REAL_WORLD_FUNCTION=executors.realWorld.functionArn;
      // Provision private executors for operational checks before admitting
      // submitted packages through the public authenticated queue.
      if (packagesEnabled) networkingEnvironment.NETWORK_PACKAGE_FUNCTION=packageExecutor.functionArn;
      executors.emulated.addToRolePolicy(new iam.PolicyStatement({actions:['ec2:DescribeInstances'],resources:['*']}));
      executors.emulated.addToRolePolicy(new iam.PolicyStatement({actions:['ec2:TerminateInstances'],resources:[cdk.Stack.of(this).formatArn({service:'ec2',resource:'instance',resourceName:'*',arnFormat:cdk.ArnFormat.SLASH_RESOURCE_NAME})],conditions:{StringEquals:{'ec2:ResourceTag/Project':'JumpServe'}}}));
    }
    const fn = new lambda.Function(this, 'Api', {
      code: lambda.Code.fromAsset(runtime, { exclude: ['tests', '__pycache__', '*.pyc', 'cli.py', 'server.py', 'bridge.py', 'README.md'] }),
      handler: 'api.handler', runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.seconds(29), memorySize: 512, reservedConcurrentExecutions: reserveConcurrency ? 4 : undefined,
      environment: { SUPABASE_URL: url, SUPABASE_ANON_KEY: this.node.tryGetContext('supabaseAnonKey') ?? '', SUPABASE_SECRET_ARN: secret.secretArn, RESEARCH_QUEUE_WORKERS_ENABLED: String(queueEnabled),...networkingEnvironment },
      description: 'Versioned research evidence; registered bounded arithmetic only, no submitted-code execution.',
    });
    secret.grantRead(fn);
    const integration = new HttpLambdaIntegration('ResearchWorkflowIntegration', fn);
    httpApi.addRoutes({ path: '/research/paper-uploads', methods: [api.HttpMethod.POST], integration });
    httpApi.addRoutes({ path: '/research/studies/{studyId}/autonomy', methods: [api.HttpMethod.GET, api.HttpMethod.POST], integration });
    for (const route of ['/research/capabilities', '/research/papers', '/research/papers/{studyId}/title', '/research/queue', '/research/studies', '/research/studies/{studyId}', '/research/studies/{studyId}/queue', '/research/studies/{studyId}/prepare', '/research/studies/{studyId}/idea', '/research/studies/{studyId}/gap-experiments', '/research/studies/{studyId}/claim-design']) httpApi.addRoutes({ path: route, methods: [api.HttpMethod.GET], integration });
    for (const route of ['/research/studies', '/research/studies/{studyId}/records', '/research/studies/{studyId}/protocols', '/research/studies/{studyId}/runs', '/research/studies/{studyId}/publish', '/research/studies/{studyId}/queue', '/research/studies/{studyId}/queue-actions', '/research/studies/{studyId}/prepare', '/research/studies/{studyId}/idea','/research/studies/{studyId}/network', '/research/studies/{studyId}/gap-experiments', '/research/studies/{studyId}/claim-design']) httpApi.addRoutes({ path: route, methods: [api.HttpMethod.POST], integration });
    if (queueEnabled) {
      const worker = new lambda.Function(this, 'QueueWorker', {
        code: lambda.Code.fromAsset(runtime), handler: 'worker.handler', runtime: lambda.Runtime.PYTHON_3_12,
        memorySize: 512, timeout: cdk.Duration.seconds(180), reservedConcurrentExecutions: reserveConcurrency ? 2 : undefined,
        retryAttempts: 0, maxEventAge: cdk.Duration.minutes(1),
        environment: { SUPABASE_URL: url, SUPABASE_SECRET_ARN: secret.secretArn,...networkingEnvironment },
        description: 'Two bounded queue slots per invocation; fenced Supabase leases, no automatic experiment retries.',
      });
      secret.grantRead(worker);
      if (boundedVersion) {
        boundedVersion.grantInvoke(worker);
        worker.addToRolePolicy(new iam.PolicyStatement({ actions: ['lambda:GetFunctionConfiguration'], resources: [boundedVersion.functionArn] }));
      }
      fn.addEnvironment('RESEARCH_QUEUE_WORKER_FUNCTION', worker.functionArn);
      worker.grantInvoke(fn);
      if (autonomyEnabled) {
        const pdfPath = path.join(__dirname, '..', '.runtime-autonomy-python');
        const pdfLock = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'autonomy-pdf-runtime.json'), 'utf8'));
        const pdfManifest = JSON.parse(fs.readFileSync(path.join(pdfPath, 'manifest.json'), 'utf8'));
        if (pdfManifest.sha256 !== pdfLock.sha256 || pdfManifest.requirement !== pdfLock.requirement || JSON.stringify(pdfManifest.files) !== JSON.stringify(pdfLock.files)) throw new Error('Autonomous PDF dependency identity differs. Run bin/prepare-autonomy-runtime.py.');
        for (const [name, hash] of Object.entries(pdfManifest.files)) {
          if (name.includes('..') || path.isAbsolute(name) || createHash('sha256').update(fs.readFileSync(path.join(pdfPath, 'python', name))).digest('hex') !== hash) throw new Error('Autonomous PDF dependency bytes differ.');
        }
        const inventory = (directory: string): string[] => fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
          if (entry.name === '__pycache__' || /\.py[co]$/.test(entry.name)) return [];
          const location = path.join(directory, entry.name);
          return entry.isDirectory() ? inventory(location) : [path.relative(pdfPath, location)];
        });
        if (inventory(pdfPath).some(name => name !== 'manifest.json' && !Object.hasOwn(pdfLock.files, name.replace(/^python\//, '')))) throw new Error('Undeclared PDF layer files cannot enter the runtime.');
        const pdfLayer = new lambda.LayerVersion(this, 'AutonomyPdfLayer', { code: lambda.Code.fromAsset(pdfPath, { exclude: ['**/__pycache__/**', '**/*.pyc', '**/*.pyo'] }), compatibleRuntimes: [lambda.Runtime.PYTHON_3_12], description: 'Hash-verified pypdf 6.19.0; text extraction is not substantive paper review.' });
        const autonomous = new lambda.Function(this, 'AutonomyWorker', {
          code: lambda.Code.fromAsset(runtime), handler: 'autonomy.handler', runtime: lambda.Runtime.PYTHON_3_12,
          memorySize: 1024, timeout: cdk.Duration.seconds(180), reservedConcurrentExecutions: reserveConcurrency ? 2 : undefined,
          retryAttempts: 0, maxEventAge: cdk.Duration.minutes(1), layers: [pdfLayer],
          environment: { SUPABASE_URL: url, SUPABASE_SECRET_ARN: secret.secretArn, RESEARCH_AUTONOMY_ENABLED: 'true', RESEARCH_AUTONOMY_CONTEXT_RECOVERY: 'autonomy-context-budget-v1', RESEARCH_QUEUE_WORKERS_ENABLED: 'true', RESEARCH_QUEUE_WORKER_FUNCTION: worker.functionArn, ...networkingEnvironment,...aiEnvironment },
          description: 'Durable parallel claim stages with atomic $100/7-day admission, uncapped AI turns, exact history and explicit blockers.',
        });
        secret.grantRead(autonomous);
        worker.grantInvoke(autonomous);
        autonomous.grantInvoke(fn);
        fn.addEnvironment('RESEARCH_AUTONOMY_ENABLED', String(autonomyAdmission));
        fn.addEnvironment('RESEARCH_AUTONOMY_WORKER_FUNCTION', autonomous.functionArn);
        if(openclawEnabled){
          fn.addEnvironment('RESEARCH_AI_RUNTIME','openclaw-production-v1');
        } else {
        const profile = 'arn:aws:bedrock:us-east-1:395567831870:inference-profile/us.anthropic.claude-opus-4-6-v1';
        autonomous.addToRolePolicy(new iam.PolicyStatement({ actions: ['bedrock:InvokeModel'], resources: [profile] }));
        autonomous.addToRolePolicy(new iam.PolicyStatement({ actions: ['bedrock:InvokeModel'], resources: ['us-east-1', 'us-east-2', 'us-west-2'].map(region => `arn:aws:bedrock:${region}::foundation-model/anthropic.claude-opus-4-6-v1`), conditions: { StringEquals: { 'bedrock:InferenceProfileArn': profile } } }));
        }
        new events.Rule(this, 'AutonomyPoll', { enabled: autonomyAdmission, schedule: events.Schedule.rate(cdk.Duration.minutes(1)), targets: [new targets.LambdaFunction(autonomous, { retryAttempts: 0, maxEventAge: cdk.Duration.minutes(1) })] });
      }
      if (networkingEnabled && executors && packageExecutor) for (const target of [executors.emulated,executors.realWorld,packageExecutor]) target.grantInvoke(worker);
      new events.Rule(this, 'QueuePoll', {
        schedule: events.Schedule.rate(cdk.Duration.minutes(1)),
        targets: [new targets.LambdaFunction(worker, { retryAttempts: 0, maxEventAge: cdk.Duration.minutes(1) })],
      });
    }
    new cdk.CfnOutput(cdk.Stack.of(this), 'ResearchWorkflowApiUrl', { value: `${httpApi.apiEndpoint}/research`, description: 'Research workflow shares the benchmark API origin.' });
  }
}
