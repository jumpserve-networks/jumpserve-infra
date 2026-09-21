import * as cdk from 'aws-cdk-lib/core';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda-nodejs';
import * as lambdaRuntime from 'aws-cdk-lib/aws-lambda';
import * as apigatewayv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigatewayv2Integrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as events from 'aws-cdk-lib/aws-events';
import * as eventsTargets from 'aws-cdk-lib/aws-events-targets';
import { Construct } from 'constructs';
import * as path from 'path';
import { addBenchmarkImagePipelineRole } from './benchmark-image-pipeline';
import { RealWorldTests } from './real-world-tests';

export class BenchmarkOrchestratorStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const supabaseUrl = this.node.tryGetContext('supabaseUrl');

    // Look up existing resources
    const vpc = ec2.Vpc.fromLookup(this, 'DefaultVpc', { isDefault: true });
    const publicSubnets = vpc.publicSubnets;

    // Supabase service key from Secrets Manager
    const supabaseSecret = secretsmanager.Secret.fromSecretNameV2(
      this, 'SupabaseServiceKey', 'jumpserve/supabase-service-key'
    );

    // Security group for benchmark instances (outbound only)
    const benchmarkSg = new ec2.SecurityGroup(this, 'BenchmarkInstanceSG', {
      vpc,
      description: 'Security group for ephemeral benchmark EC2 instances',
      allowAllOutbound: true,
    });

    // IAM role for benchmark EC2 instances
    const benchmarkInstanceRole = new iam.Role(this, 'BenchmarkInstanceRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
      ],
    });

    // Allow self-termination
    benchmarkInstanceRole.addToPolicy(new iam.PolicyStatement({
      actions: ['ec2:TerminateInstances'],
      resources: ['*'],
      conditions: {
        StringEquals: { 'aws:ResourceTag/Project': 'JumpServe' },
      },
    }));

    // An EC2 runner must never be able to retrieve a database credential.
    benchmarkInstanceRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.DENY,
      actions: ['secretsmanager:GetSecretValue', 'secretsmanager:BatchGetSecretValue'],
      resources: ['*'],
    }));

    // Allow CloudWatch Logs for log streaming
    benchmarkInstanceRole.addToPolicy(new iam.PolicyStatement({
      actions: [
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents',
        'logs:DescribeLogStreams',
      ],
      resources: ['arn:aws:logs:*:*:log-group:/jumpserve/benchmark*'],
    }));

    // Instance profile for benchmark instances
    const instanceProfile = new iam.CfnInstanceProfile(this, 'BenchmarkInstanceProfile', {
      roles: [benchmarkInstanceRole.roleName],
    });

    // Keep the base-image path for rollback. CloudFormation retains this
    // parameter on later deployments, unlike a one-off Lambda environment edit.
    const benchmarkAmi = new cdk.CfnParameter(this, 'BenchmarkAmiId', {
      type: 'String',
      default: '',
      allowedPattern: '^(|ami-([0-9a-f]{8}|[0-9a-f]{17}))$',
      description: 'Private AMI created by ami/build.py; empty uses Ubuntu with installation at boot',
    });
    const useBenchmarkAmi = new cdk.CfnCondition(this, 'UseBenchmarkAmi', {
      expression: cdk.Fn.conditionNot(cdk.Fn.conditionEquals(benchmarkAmi.valueAsString, '')),
    });
    const ubuntuAmi = ec2.MachineImage.fromSsmParameter(
      '/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id'
    );
    const amiId = cdk.Fn.conditionIf(
      useBenchmarkAmi.logicalId, benchmarkAmi.valueAsString, ubuntuAmi.getImage(this).imageId,
    ).toString();

    // Lambda: launch benchmark
    const launchFn = new lambda.NodejsFunction(this, 'LaunchBenchmarkFn', {
      entry: path.join(__dirname, '..', 'lambda', 'launch-benchmark', 'index.ts'),
      handler: 'handler',
      runtime: lambdaRuntime.Runtime.NODEJS_22_X,
      timeout: cdk.Duration.seconds(30),
      memorySize: 256,
      environment: {
        SUPABASE_URL: supabaseUrl,
        SUPABASE_ANON_KEY: this.node.tryGetContext('supabaseAnonKey') ?? '',
        SUPABASE_SECRET_ARN: supabaseSecret.secretArn,
        AMI_ID: amiId,
        BENCHMARK_IMAGE_MODE: cdk.Fn.conditionIf(useBenchmarkAmi.logicalId, 'prebaked', 'base').toString(),
        SECURITY_GROUP_ID: benchmarkSg.securityGroupId,
        SUBNET_ID: publicSubnets[0].subnetId,
        INSTANCE_PROFILE_ARN: instanceProfile.attrArn,
      },
      bundling: {
        externalModules: ['@aws-sdk/*'],
      },
    });

    // Lambda permissions
    supabaseSecret.grantRead(launchFn);

    launchFn.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'ec2:RunInstances',
        'ec2:CreateTags',
        'ec2:DescribeInstances',
        'ec2:DescribeSubnets',
        'ec2:DescribeSecurityGroups',
      ],
      resources: ['*'],
    }));

    launchFn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['iam:PassRole'],
      resources: [benchmarkInstanceRole.roleArn],
    }));

    const imagePipelineRole = addBenchmarkImagePipelineRole(this, benchmarkInstanceRole, launchFn.functionArn);
    supabaseSecret.grantRead(imagePipelineRole);

    // Lambda: cleanup stale benchmarks
    const cleanupFn = new lambda.NodejsFunction(this, 'CleanupBenchmarksFn', {
      entry: path.join(__dirname, '..', 'lambda', 'cleanup-benchmarks', 'index.ts'),
      handler: 'handler',
      runtime: lambdaRuntime.Runtime.NODEJS_22_X,
      timeout: cdk.Duration.seconds(60),
      memorySize: 256,
      environment: {
        SUPABASE_URL: supabaseUrl,
        SUPABASE_ANON_KEY: this.node.tryGetContext('supabaseAnonKey') ?? '',
        SUPABASE_SECRET_ARN: supabaseSecret.secretArn,
      },
      bundling: {
        externalModules: ['@aws-sdk/*'],
      },
    });

    supabaseSecret.grantRead(cleanupFn);

    cleanupFn.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'ec2:DescribeInstances',
        'ec2:TerminateInstances',
      ],
      resources: ['*'],
    }));

    // EventBridge: run cleanup every 15 minutes
    new events.Rule(this, 'CleanupSchedule', {
      schedule: events.Schedule.rate(cdk.Duration.minutes(15)),
      targets: [new eventsTargets.LambdaFunction(cleanupFn)],
    });

    // Lambda: cancel a running benchmark
    const cancelFn = new lambda.NodejsFunction(this, 'CancelBenchmarkFn', {
      entry: path.join(__dirname, '..', 'lambda', 'cancel-benchmark', 'index.ts'),
      handler: 'handler',
      runtime: lambdaRuntime.Runtime.NODEJS_22_X,
      timeout: cdk.Duration.seconds(15),
      memorySize: 256,
      environment: {
        SUPABASE_URL: supabaseUrl,
        SUPABASE_ANON_KEY: this.node.tryGetContext('supabaseAnonKey') ?? '',
        SUPABASE_SECRET_ARN: supabaseSecret.secretArn,
      },
      bundling: {
        externalModules: ['@aws-sdk/*'],
      },
    });

    supabaseSecret.grantRead(cancelFn);

    cancelFn.addToRolePolicy(new iam.PolicyStatement({
      actions: ['ec2:TerminateInstances'],
      resources: ['*'],
    }));

    // Lambda: get benchmark logs from CloudWatch
    const getLogsFn = new lambda.NodejsFunction(this, 'GetBenchmarkLogsFn', {
      entry: path.join(__dirname, '..', 'lambda', 'get-benchmark-logs', 'index.ts'),
      handler: 'handler',
      runtime: lambdaRuntime.Runtime.NODEJS_22_X,
      timeout: cdk.Duration.seconds(15),
      memorySize: 256,
      bundling: {
        externalModules: ['@aws-sdk/*'],
      },
    });

    getLogsFn.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'logs:GetLogEvents',
        'logs:DescribeLogStreams',
      ],
      resources: ['arn:aws:logs:*:*:log-group:/jumpserve/benchmark*'],
    }));

    // HTTP API Gateway
    const httpApi = new apigatewayv2.HttpApi(this, 'BenchmarkApi', {
      apiName: 'JumpServeBenchmarkApi',
      corsPreflight: {
        allowOrigins: ['*'],
        allowMethods: [apigatewayv2.CorsHttpMethod.GET, apigatewayv2.CorsHttpMethod.POST, apigatewayv2.CorsHttpMethod.OPTIONS],
        allowHeaders: ['Content-Type', 'Authorization'],
      },
    });

    httpApi.addRoutes({
      path: '/benchmarks',
      methods: [apigatewayv2.HttpMethod.POST],
      integration: new apigatewayv2Integrations.HttpLambdaIntegration(
        'LaunchBenchmarkIntegration', launchFn
      ),
    });

    const ingestFn = new lambda.NodejsFunction(this, 'BenchmarkIngestFn', {
      entry: path.join(__dirname, '..', 'lambda', 'benchmark-ingest', 'index.ts'),
      handler: 'handler', runtime: lambdaRuntime.Runtime.NODEJS_22_X,
      timeout: cdk.Duration.seconds(60), memorySize: 512,
      environment: { SUPABASE_URL: supabaseUrl, SUPABASE_SECRET_ARN: supabaseSecret.secretArn },
      bundling: { externalModules: ['@aws-sdk/*'] },
    });
    supabaseSecret.grantRead(ingestFn);
    httpApi.addRoutes({
      path: '/benchmarks/ingest', methods: [apigatewayv2.HttpMethod.POST],
      integration: new apigatewayv2Integrations.HttpLambdaIntegration('BenchmarkIngestIntegration', ingestFn),
    });
    launchFn.addEnvironment('BENCHMARK_INGEST_URL', `${httpApi.apiEndpoint}/benchmarks/ingest`);

    httpApi.addRoutes({
      path: '/benchmarks/cancel',
      methods: [apigatewayv2.HttpMethod.POST],
      integration: new apigatewayv2Integrations.HttpLambdaIntegration(
        'CancelBenchmarkIntegration', cancelFn
      ),
    });

    httpApi.addRoutes({
      path: '/benchmarks/logs',
      methods: [apigatewayv2.HttpMethod.GET],
      integration: new apigatewayv2Integrations.HttpLambdaIntegration(
        'GetBenchmarkLogsIntegration', getLogsFn
      ),
    });

    new RealWorldTests(this, 'RealWorldTests', httpApi);

    new cdk.CfnOutput(this, 'BenchmarkApiUrl', {
      value: httpApi.apiEndpoint,
      description: 'Benchmark API Gateway URL',
    });

    new cdk.CfnOutput(this, 'BenchmarkSecurityGroupId', {
      value: benchmarkSg.securityGroupId,
      description: 'Security group for benchmark instances',
    });

    new cdk.CfnOutput(this, 'BenchmarkImageId', {
      value: amiId,
      description: 'AMI used for new benchmark instances',
    });
  }
}
