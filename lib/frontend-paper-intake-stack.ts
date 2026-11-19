import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as path from 'node:path';
import {Construct} from 'constructs';

/** Adds runtime credentials to the existing Amplify app without replacing it. */
export class FrontendPaperIntakeStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope,id,props);
    const appArn=`arn:${this.partition}:amplify:${this.region}:${this.account}:apps/d24jvguj7brnkj`;
    const secret=new secretsmanager.Secret(this,'Credentials',{
      secretName:'jumpserve/frontend/paper-intake',
      description:'Server-only OpenAI and Supabase credentials for Next.js phase-one paper intake.',
    });
    secret.applyRemovalPolicy(cdk.RemovalPolicy.RETAIN);
    const role=new iam.Role(this,'ComputeRole',{
      roleName:'JumpServeFrontendPaperIntake',
      assumedBy:new iam.ServicePrincipal('amplify.amazonaws.com',{conditions:{
        StringEquals:{'aws:SourceAccount':this.account},
        ArnLike:{'aws:SourceArn':[appArn,`${appArn}/branches/main`]},
      }}),
      description:'Production Amplify SSR: read only the paper-intake credential secret.',
    });
    role.addToPolicy(new iam.PolicyStatement({actions:['secretsmanager:GetSecretValue'],resources:[secret.secretArn]}));
    const continuation=new lambda.Function(this,'PaperContinuation',{
      runtime:lambda.Runtime.PYTHON_3_12,handler:'index.handler',
      code:lambda.Code.fromAsset(path.join(__dirname,'../assets/frontend-paper-continuation'),{exclude:['**/__pycache__/**','**/*.pyc']}),
      // This account has only the mandatory unreserved pool. Durable database
      // leases and original admission guards handle overlapping wake-ups.
      timeout:cdk.Duration.seconds(100),memorySize:128,
      environment:{SECRET_ARN:secret.secretArn},logGroup:new logs.LogGroup(this,'PaperContinuationLogs',{retention:logs.RetentionDays.ONE_MONTH,removalPolicy:cdk.RemovalPolicy.RETAIN}),
      description:'Wake the Next.js paper controller for saved Step 2–4 work; no model or experiment execution.',
    });
    continuation.addToRolePolicy(new iam.PolicyStatement({actions:['secretsmanager:GetSecretValue'],resources:[secret.secretArn]}));
    continuation.configureAsyncInvoke({retryAttempts:0,maxEventAge:cdk.Duration.minutes(1)});
    new events.Rule(this,'PaperContinuationSchedule',{
      schedule:events.Schedule.rate(cdk.Duration.minutes(1)),
      targets:[new targets.LambdaFunction(continuation,{retryAttempts:0,maxEventAge:cdk.Duration.minutes(1)})],
    });
    new cdk.CfnOutput(this,'SecretArn',{value:secret.secretArn});
    new cdk.CfnOutput(this,'ComputeRoleArn',{value:role.roleArn});
  }
}
