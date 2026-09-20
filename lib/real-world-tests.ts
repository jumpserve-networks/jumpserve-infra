import * as cdk from 'aws-cdk-lib';
import * as api from 'aws-cdk-lib/aws-apigatewayv2';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import { Construct } from 'constructs';
import * as path from 'path';
import * as fs from 'fs';

export class RealWorldTests extends Construct {
  constructor(scope: Construct, id: string, httpApi: api.HttpApi) {
    super(scope, id);
    const runtimePath = process.env.REAL_WORLD_RUNTIME_PATH ?? path.join(__dirname, '..', '.runtime-backend', 'real_world');
    const revision = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'real-world-runtime.json'), 'utf8')).revision as string;
    if (!fs.existsSync(path.join(runtimePath, 'controller.py'))) {
      throw new Error('Fetch the pinned backend runtime (see README) or set REAL_WORLD_RUNTIME_PATH to jumpserve-back-end/real_world.');
    }
    const code = lambda.Code.fromAsset(runtimePath, { exclude: ['__pycache__', '*.pyc', 'tests'] });
    const table = new dynamodb.Table(this, 'Jobs', {
      partitionKey: { name: 'job_id', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true },
      removalPolicy: cdk.RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE,
    });
    table.addGlobalSecondaryIndex({ indexName: 'owner-created',
      partitionKey: { name: 'owner', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'created_at', type: dynamodb.AttributeType.NUMBER } });
    table.addGlobalSecondaryIndex({ indexName: 'active-deadline',
      partitionKey: { name: 'active', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'deadline', type: dynamodb.AttributeType.NUMBER } });
    const results = new s3.Bucket(this, 'Results', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL, encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true, versioned: true, removalPolicy: cdk.RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE,
    });
    const instanceRole = new iam.Role(this, 'InstanceRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore')],
    });
    const profile = new iam.CfnInstanceProfile(this, 'InstanceProfile', { roles: [instanceRole.roleName] });
    const environment = { TABLE_NAME: table.tableName, RESULTS_BUCKET: results.bucketName,
      INSTANCE_PROFILE_ARN: profile.attrArn, RUNTIME_REVISION: revision };
    const workerRole = new iam.Role(this, 'WorkerRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole')],
    });
    workerRole.addToPolicy(new iam.PolicyStatement({ actions: ['ec2:Describe*', 'ssm:DescribeInstanceInformation', 'ssm:GetCommandInvocation'], resources: ['*'] }));
    workerRole.addToPolicy(new iam.PolicyStatement({ actions: ['ssm:GetParameter'], resources: ['arn:aws:ssm:*::parameter/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id'] }));
    workerRole.addToPolicy(new iam.PolicyStatement({ actions: ['iam:PassRole'], resources: [instanceRole.roleArn], conditions: { StringEquals: { 'iam:PassedToService': 'ec2.amazonaws.com' } } }));
    const tagged = { StringEquals: { 'ec2:ResourceTag/Project': 'JumpServeRealWorld' } };
    const stack = cdk.Stack.of(this);
    const ec2Arn = (resource: string) => `arn:${stack.partition}:ec2:*:${stack.account}:${resource}/*`;
    workerRole.addToPolicy(new iam.PolicyStatement({ actions: ['ec2:RunInstances'], resources: [
      `arn:${stack.partition}:ec2:*::image/*`, ec2Arn('instance'), ec2Arn('volume'), ec2Arn('network-interface'),
    ] }));
    workerRole.addToPolicy(new iam.PolicyStatement({ actions: ['ec2:RunInstances'], resources: [ec2Arn('subnet'), ec2Arn('security-group')], conditions: tagged }));
    workerRole.addToPolicy(new iam.PolicyStatement({ actions: ['ec2:CreateVpc', 'ec2:CreateSubnet', 'ec2:CreateInternetGateway', 'ec2:CreateSecurityGroup', 'ec2:CreateRouteTable'], resources: ['*'] }));
    workerRole.addToPolicy(new iam.PolicyStatement({ actions: ['ec2:CreateTags'], resources: ['*'], conditions: {
      StringEquals: { 'ec2:CreateAction': ['CreateVpc', 'CreateSubnet', 'CreateInternetGateway', 'CreateSecurityGroup', 'CreateRouteTable', 'RunInstances'] },
    } }));
    workerRole.addToPolicy(new iam.PolicyStatement({ actions: [
      'ec2:ModifyVpcAttribute', 'ec2:AttachInternetGateway', 'ec2:DetachInternetGateway', 'ec2:CreateRoute',
      'ec2:AssociateRouteTable', 'ec2:DisassociateRouteTable', 'ec2:AuthorizeSecurityGroupIngress',
      'ec2:TerminateInstances', 'ec2:DeleteSubnet', 'ec2:DeleteSecurityGroup', 'ec2:DeleteInternetGateway', 'ec2:DeleteRouteTable', 'ec2:DeleteVpc',
    ], resources: ['*'], conditions: tagged }));
    workerRole.addToPolicy(new iam.PolicyStatement({ actions: ['ssm:SendCommand'], resources: [`arn:${stack.partition}:ssm:*::document/AWS-RunShellScript`] }));
    workerRole.addToPolicy(new iam.PolicyStatement({ actions: ['ssm:SendCommand'], resources: [ec2Arn('instance')], conditions: { StringEquals: { 'ssm:resourceTag/Project': 'JumpServeRealWorld' } } }));
    table.grantReadWriteData(workerRole);
    results.grantReadWrite(workerRole);
    const worker = new lambda.Function(this, 'Worker', { code, handler: 'controller.handler', runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.minutes(4), memorySize: 512, environment, role: workerRole });
    const reaper = new lambda.Function(this, 'Reaper', { code, handler: 'controller.reap', runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.minutes(4), memorySize: 512, environment, role: workerRole });
    new events.Rule(this, 'ReapSchedule', { schedule: events.Schedule.rate(cdk.Duration.minutes(5)), targets: [new targets.LambdaFunction(reaper)] });
    const tick = new tasks.LambdaInvoke(this, 'Advance test', { lambdaFunction: worker, payloadResponseOnly: true });
    const recover = new tasks.LambdaInvoke(this, 'Clean up interrupted test', { lambdaFunction: worker, payloadResponseOnly: true,
      payload: sfn.TaskInput.fromObject({ 'job_id.$': '$.job_id', force_cleanup: true }) });
    tick.addRetry({ errors: ['States.ALL'], interval: cdk.Duration.seconds(10), maxAttempts: 3 });
    tick.addCatch(recover, { resultPath: '$.workflow_error' });
    const wait = new sfn.Wait(this, 'Wait for machines', { time: sfn.WaitTime.duration(cdk.Duration.seconds(15)) });
    const done = new sfn.Choice(this, 'Resources cleaned?').when(sfn.Condition.booleanEquals('$.finished', true), new sfn.Succeed(this, 'Finished')).otherwise(wait);
    wait.next(tick);
    tick.next(done);
    recover.next(done);
    const machine = new sfn.StateMachine(this, 'Lifecycle', { definitionBody: sfn.DefinitionBody.fromChainable(tick), timeout: cdk.Duration.hours(2) });
    const service = new lambda.Function(this, 'Api', { code, handler: 'api.handler', runtime: lambda.Runtime.PYTHON_3_12,
      timeout: cdk.Duration.seconds(29), memorySize: 512, environment: { ...environment,
        SUPABASE_URL: this.node.tryGetContext('supabaseUrl'), SUPABASE_ANON_KEY: this.node.tryGetContext('supabaseAnonKey') ?? '', STATE_MACHINE_ARN: machine.stateMachineArn } });
    table.grantReadWriteData(service);
    results.grantRead(service);
    machine.grantStartExecution(service);
    service.addToRolePolicy(new iam.PolicyStatement({ actions: ['ec2:DescribeRegions', 'ec2:DescribeAvailabilityZones', 'ec2:DescribeInstanceTypeOfferings'], resources: ['*'] }));
    const integration = new HttpLambdaIntegration('RealWorldIntegration', service);
    for (const route of ['/real-world/regions', '/real-world/locations', '/real-world/tests', '/real-world/tests/{jobId}', '/real-world/tests/{jobId}/artifacts']) {
      httpApi.addRoutes({ path: route, methods: [api.HttpMethod.GET], integration });
    }
    for (const route of ['/real-world/tests', '/real-world/tests/{jobId}/cancel']) {
      httpApi.addRoutes({ path: route, methods: [api.HttpMethod.POST], integration });
    }
    new cdk.CfnOutput(stack, 'RealWorldResultsBucket', { value: results.bucketName });
    new cdk.CfnOutput(stack, 'RealWorldJobsTable', { value: table.tableName });
  }
}
