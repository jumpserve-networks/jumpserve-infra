import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
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
    new cdk.CfnOutput(this,'SecretArn',{value:secret.secretArn});
    new cdk.CfnOutput(this,'ComputeRoleArn',{value:role.roleArn});
  }
}
