import * as cdk from 'aws-cdk-lib';
import {Template,Match} from 'aws-cdk-lib/assertions';
import {FrontendPaperIntakeStack} from '../lib/frontend-paper-intake-stack';
test('local skill architecture retains result-read credentials without background assessment compute',()=>{
 const app=new cdk.App({context:{localAssessmentsOnly:true}});
 const template=Template.fromStack(new FrontendPaperIntakeStack(app,'LocalResults',{env:{account:'395567831870',region:'us-east-1'}}));
 template.resourceCountIs('AWS::Lambda::Function',0);template.resourceCountIs('AWS::Events::Rule',0);
 template.resourceCountIs('AWS::SecretsManager::Secret',1);template.resourceCountIs('AWS::IAM::Role',1);
});
test('paper-intake runtime role can read only its retained secret and trusts the production app',()=>{
 const app=new cdk.App();const template=Template.fromStack(new FrontendPaperIntakeStack(app,'Intake',{env:{account:'395567831870',region:'us-east-1'}}));
 template.resourceCountIs('AWS::Amplify::App',0);template.resourceCountIs('AWS::Amplify::Branch',0);
 template.hasResourceProperties('AWS::SecretsManager::Secret',{Name:'jumpserve/frontend/paper-intake'});
 template.hasResourceProperties('AWS::IAM::Role',{RoleName:'JumpServeFrontendPaperIntake',AssumeRolePolicyDocument:{Statement:Match.arrayWith([Match.objectLike({Principal:{Service:'amplify.amazonaws.com'},Condition:{StringEquals:{'aws:SourceAccount':'395567831870'},ArnLike:{'aws:SourceArn':[{'Fn::Join':['',['arn:',{Ref:'AWS::Partition'},':amplify:us-east-1:395567831870:apps/d24jvguj7brnkj']]},{'Fn::Join':['',['arn:',{Ref:'AWS::Partition'},':amplify:us-east-1:395567831870:apps/d24jvguj7brnkj/branches/main']]}]}}})])}});
 const policies=Object.values(template.findResources('AWS::IAM::Policy'));
 const compute=policies.find((policy:any)=>policy.Properties.PolicyName.startsWith('ComputeRoleDefaultPolicy'));
 expect(compute).toBeDefined();expect(compute!.Properties.PolicyDocument.Statement).toHaveLength(1);expect(compute!.Properties.PolicyDocument.Statement[0]).toMatchObject({Action:'secretsmanager:GetSecretValue',Effect:'Allow'});expect(compute!.Properties.PolicyDocument.Statement[0].Resource).toHaveProperty('Ref');
 const secret=Object.values(template.findResources('AWS::SecretsManager::Secret'))[0];expect(secret.DeletionPolicy).toBe('Retain');
 expect(secret.Properties.SecretString).toBeUndefined();expect(JSON.stringify(template.toJSON())).not.toMatch(/sk-proj-|sb_secret_/);
});
test('paper continuation only wakes the Next.js controller on a bounded schedule',()=>{
 const app=new cdk.App();const template=Template.fromStack(new FrontendPaperIntakeStack(app,'Continuation',{env:{account:'395567831870',region:'us-east-1'}}));
 template.hasResourceProperties('AWS::Lambda::Function',{Runtime:'python3.12',Handler:'index.handler',Timeout:100,MemorySize:128,ReservedConcurrentExecutions:Match.absent(),Environment:{Variables:{SECRET_ARN:Match.anyValue()}}});
 template.hasResourceProperties('AWS::Lambda::EventInvokeConfig',{MaximumRetryAttempts:0,MaximumEventAgeInSeconds:60});
 template.hasResourceProperties('AWS::Events::Rule',{ScheduleExpression:'rate(1 minute)',Targets:Match.arrayWith([Match.objectLike({RetryPolicy:{MaximumEventAgeInSeconds:60,MaximumRetryAttempts:0}})])});
 const policies=Object.values(template.findResources('AWS::IAM::Policy')) as any[];
 const continuation=policies.find(policy=>policy.Properties.PolicyName.startsWith('PaperContinuationServiceRoleDefaultPolicy'));
 expect(continuation).toBeDefined();expect(continuation.Properties.PolicyDocument.Statement).toHaveLength(1);
 expect(continuation.Properties.PolicyDocument.Statement[0]).toMatchObject({Action:'secretsmanager:GetSecretValue',Effect:'Allow'});
 expect(JSON.stringify(template.toJSON())).not.toMatch(/supabase\.co|sk-proj-|sb_secret_/);
});
