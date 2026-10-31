import * as cdk from 'aws-cdk-lib/core';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';

/** Persistent service authorization. No human SSO session or static AWS key. */
export class PlatformSupervisorAccess extends Construct {
  readonly releaseRole: iam.Role;
  readonly executionRole: iam.Role;
  constructor(scope: Construct, id: string, props: { workerRoleName: string; assetBucketName: string; apiIds: string[] }) {
    super(scope, id);
    const stack = cdk.Stack.of(this);
    if (stack.account !== '395567831870' || stack.region !== 'us-east-1') throw new Error('Fixed JumpServe AWS target required.');
    if (!/^JumpServeOpenClawStack-[A-Za-z0-9_-]+$/.test(props.workerRoleName) || !/^cdk-[a-z0-9-]+-assets-395567831870-us-east-1$/.test(props.assetBucketName) || !props.apiIds.length || props.apiIds.some(value => !/^[a-z0-9]{10}$/.test(value))) throw new Error('Discover the existing worker role, asset bucket and API IDs before synthesis.');
    const arn = (service: string, resource: string, account = stack.account) => `arn:aws:${service}:${service === 'iam' ? '' : stack.region}:${account}:${resource}`;
    const stacks = ['JumpServeBenchmarkStack', 'JumpServeAgentStack'].map(name => arn('cloudformation', `stack/${name}/*`));
    const functionArns = ['JumpServeBenchmarkStack-*', 'JumpServeAgentStack-*'].map(name => arn('lambda', `function:${name}`));
    this.executionRole = new iam.Role(this, 'Execution', {
      roleName: 'JumpServePlatformCloudFormation',
      assumedBy: new iam.ServicePrincipal('cloudformation.amazonaws.com'),
      description: 'Scoped platform template execution; cannot change IAM, EC2, storage or the supervisor authority.',
    });
    const allowExecution = (actions: string[], resources: string[], conditions?: Record<string, Record<string, unknown>>) => this.executionRole.addToPolicy(new iam.PolicyStatement({ actions, resources, conditions }));
    allowExecution(['lambda:GetFunction', 'lambda:GetFunctionConfiguration', 'lambda:GetPolicy', 'lambda:ListTags', 'lambda:UpdateFunctionCode', 'lambda:UpdateFunctionConfiguration', 'lambda:PublishVersion', 'lambda:TagResource', 'lambda:UntagResource', 'lambda:AddPermission', 'lambda:RemovePermission'], functionArns);
    allowExecution(['lambda:GetLayerVersion', 'lambda:PublishLayerVersion', 'lambda:DeleteLayerVersion'], [arn('lambda', 'layer:JumpServe*')]);
    allowExecution(['apigateway:GET', 'apigateway:POST', 'apigateway:PUT', 'apigateway:PATCH', 'apigateway:DELETE'], props.apiIds.flatMap(api => ['apis', 'restapis'].flatMap(kind => [arn('apigateway', `/${kind}/${api}`, ''), arn('apigateway', `/${kind}/${api}/*`, '')])));
    allowExecution(['events:DescribeRule', 'events:PutRule', 'events:PutTargets', 'events:RemoveTargets', 'events:EnableRule', 'events:DisableRule', 'events:ListTargetsByRule', 'events:TagResource', 'events:UntagResource'], [arn('events', 'rule/JumpServeBenchmarkStack-*'), arn('events', 'rule/JumpServeAgentStack-*')]);
    allowExecution(['logs:CreateLogGroup', 'logs:PutRetentionPolicy', 'logs:DescribeLogGroups', 'logs:TagResource', 'logs:UntagResource'], [arn('logs', 'log-group:/aws/lambda/JumpServe*')]);
    allowExecution(['s3:GetObject'], [`arn:aws:s3:::${props.assetBucketName}/*`]);
    // CloudFormation resolves existing Role Arn attributes even for code-only
    // Lambda updates. Metadata reads do not grant IAM mutation authority.
    allowExecution(['iam:GetRole'], [arn('iam', 'role/JumpServeBenchmarkStack-*'), arn('iam', 'role/JumpServeAgentStack-*')]);
    allowExecution(['iam:PassRole'], [arn('iam', 'role/JumpServeBenchmarkStack-*'), arn('iam', 'role/JumpServeAgentStack-*')], { StringEquals: { 'iam:PassedToService': 'lambda.amazonaws.com' } });
    this.releaseRole = new iam.Role(this, 'Release', {
      roleName: 'JumpServePlatformRelease', maxSessionDuration: cdk.Duration.hours(2),
      assumedBy: new iam.WebIdentityPrincipal(arn('iam', 'oidc-provider/token.actions.githubusercontent.com'), { StringEquals: {
        'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
        'token.actions.githubusercontent.com:sub': 'repo:jumpserve-networks/jumpserve-infra:ref:refs/heads/main',
      } }),
    });
    const allowRelease = (actions: string[], resources: string[], conditions?: Record<string, Record<string, unknown>>) => this.releaseRole.addToPolicy(new iam.PolicyStatement({ actions, resources, conditions }));
    allowRelease(['cloudformation:DescribeStacks', 'cloudformation:GetTemplate', 'cloudformation:DescribeStackEvents', 'cloudformation:UpdateStack'], stacks);
    allowRelease(['cloudformation:DescribeStacks'], [arn('cloudformation', 'stack/JumpServeAmplifyStack/*')]);
    allowRelease(['iam:PassRole'], [this.executionRole.roleArn], { StringEquals: { 'iam:PassedToService': 'cloudformation.amazonaws.com' } });
    allowRelease(['amplify:ListJobs', 'amplify:GetJob'], [arn('amplify', 'apps/*/branches/main/jobs/*'), arn('amplify', 'apps/*/branches/main')]);
    allowRelease(['s3:GetObject', 's3:PutObject'], [`arn:aws:s3:::${props.assetBucketName}/*`]);
    // The existing EC2 instance profile refreshes credentials through IMDSv2.
    // It reads only service secrets; release powers remain in the OIDC job.
    const worker = iam.Role.fromRoleName(this, 'ExistingWorker', props.workerRoleName);
    new iam.Policy(this, 'WorkerSecrets', { roles: [worker], statements: [new iam.PolicyStatement({ actions: ['secretsmanager:GetSecretValue'], resources: [arn('secretsmanager', 'secret:jumpserve/platform-supervisor-*')] }), new iam.PolicyStatement({ actions: ['s3:GetObject'], resources: [`arn:aws:s3:::${props.assetBucketName}/platform-supervisor/*`] })] });
    new cdk.CfnOutput(stack, 'PlatformReleaseRoleArn', { value: this.releaseRole.roleArn });
  }
}
