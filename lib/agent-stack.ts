import * as cdk from 'aws-cdk-lib/core';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import { Construct } from 'constructs';
import * as path from 'path';

export class AgentStack extends cdk.Stack {
  public readonly functionUrl: string;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const supabaseUrl = this.node.tryGetContext('supabaseUrl');
    const benchmarkApiUrl = this.node.tryGetContext('benchmarkApiUrl');

    const supabaseSecret = secretsmanager.Secret.fromSecretNameV2(
      this, 'SupabaseServiceKey', 'jumpserve/supabase-service-key'
    );

    // Lambda function from Docker image
    const agentFn = new lambda.DockerImageFunction(this, 'AgentFn', {
      code: lambda.DockerImageCode.fromImageAsset(
        path.join(__dirname, '..', 'agent')
      ),
      memorySize: 1024,
      timeout: cdk.Duration.seconds(120),
      environment: {
        SUPABASE_URL: supabaseUrl,
        SUPABASE_SECRET_ARN: supabaseSecret.secretArn,
        BENCHMARK_API_URL: benchmarkApiUrl,
      },
      architecture: lambda.Architecture.X86_64,
    });

    // Bedrock model access
    agentFn.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream',
      ],
      resources: ['arn:aws:bedrock:*::foundation-model/anthropic.*', 'arn:aws:bedrock:*::foundation-model/us.anthropic.*'],
    }));

    // Secrets Manager access
    supabaseSecret.grantRead(agentFn);

    // Function URL with CORS
    const fnUrl = agentFn.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ['*'],
        allowedMethods: [lambda.HttpMethod.POST],
        allowedHeaders: ['Content-Type'],
      },
    });

    new cdk.CfnOutput(this, 'AgentFunctionUrl', {
      value: fnUrl.url,
      description: 'Agent Lambda Function URL',
    });
  }
}
