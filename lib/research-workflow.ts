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

export function researchWorkflowIsEnabled(value: unknown): boolean {
  return value === true || value === 'true';
}

export class ResearchWorkflow extends Construct {
  constructor(scope: Construct, id: string, httpApi: api.HttpApi) {
    super(scope, id);
    if (cdk.Stack.of(this).account !== '395567831870') throw new Error('Research workflow requires AWS account 395567831870.');
    const runtime = process.env.RESEARCH_WORKFLOW_RUNTIME_PATH ?? path.join(__dirname, '..', '.runtime-backend', 'research_workflow');
    const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'research-workflow-runtime.json'), 'utf8')) as { files: Record<string, string> };
    for (const [file, sha256] of Object.entries(manifest.files)) {
      if (!/^[a-z_]+\.py$/.test(file) || !fs.existsSync(path.join(runtime, file)) || createHash('sha256').update(fs.readFileSync(path.join(runtime, file))).digest('hex') !== sha256) {
        throw new Error('Research runtime is absent or differs from the manifest. Run bin/prepare-research-runtime.py with the documented backend checkout.');
      }
    }
    const url = this.node.tryGetContext('supabaseUrl');
    if (url !== 'https://regphejnlvfpyokpniny.supabase.co') throw new Error('Research workflow requires the verified JumpServe Supabase project.');
    const secret = secretsmanager.Secret.fromSecretNameV2(this, 'SupabaseServiceKey', 'jumpserve/supabase-service-key');
    const queueEnabled = researchWorkflowIsEnabled(this.node.tryGetContext('researchQueueEnabled'));
    const reservationContext = this.node.tryGetContext('researchReservedConcurrencyEnabled');
    const reserveConcurrency = reservationContext !== false && reservationContext !== 'false';
    const fn = new lambda.Function(this, 'Api', {
      code: lambda.Code.fromAsset(runtime, { exclude: ['tests', '__pycache__', '*.pyc', 'cli.py', 'server.py', 'bridge.py', 'README.md'] }),
      handler: 'api.handler', runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.seconds(29), memorySize: 512, reservedConcurrentExecutions: reserveConcurrency ? 4 : undefined,
      environment: { SUPABASE_URL: url, SUPABASE_ANON_KEY: this.node.tryGetContext('supabaseAnonKey') ?? '', SUPABASE_SECRET_ARN: secret.secretArn, RESEARCH_QUEUE_WORKERS_ENABLED: String(queueEnabled) },
      description: 'Versioned research evidence; registered bounded arithmetic only, no submitted-code execution.',
    });
    secret.grantRead(fn);
    const integration = new HttpLambdaIntegration('ResearchWorkflowIntegration', fn);
    for (const route of ['/research/capabilities', '/research/studies', '/research/studies/{studyId}', '/research/studies/{studyId}/queue']) httpApi.addRoutes({ path: route, methods: [api.HttpMethod.GET], integration });
    for (const route of ['/research/studies', '/research/studies/{studyId}/records', '/research/studies/{studyId}/protocols', '/research/studies/{studyId}/runs', '/research/studies/{studyId}/publish', '/research/studies/{studyId}/queue', '/research/studies/{studyId}/queue-actions']) httpApi.addRoutes({ path: route, methods: [api.HttpMethod.POST], integration });
    if (queueEnabled) {
      const worker = new lambda.Function(this, 'QueueWorker', {
        code: lambda.Code.fromAsset(runtime), handler: 'worker.handler', runtime: lambda.Runtime.PYTHON_3_12,
        memorySize: 512, timeout: cdk.Duration.seconds(180), reservedConcurrentExecutions: reserveConcurrency ? 2 : undefined,
        retryAttempts: 0, maxEventAge: cdk.Duration.minutes(1),
        environment: { SUPABASE_URL: url, SUPABASE_SECRET_ARN: secret.secretArn },
        description: 'Two bounded queue slots per invocation; fenced Supabase leases, no automatic experiment retries.',
      });
      secret.grantRead(worker);
      new events.Rule(this, 'QueuePoll', {
        schedule: events.Schedule.rate(cdk.Duration.minutes(1)),
        targets: [new targets.LambdaFunction(worker, { retryAttempts: 0, maxEventAge: cdk.Duration.minutes(1) })],
      });
    }
    new cdk.CfnOutput(cdk.Stack.of(this), 'ResearchWorkflowApiUrl', { value: `${httpApi.apiEndpoint}/research`, description: 'Research workflow shares the benchmark API origin.' });
  }
}
