import * as cdk from 'aws-cdk-lib';
import {Template,Match} from 'aws-cdk-lib/assertions';
import {FrontendPaperIntakeStack} from '../lib/frontend-paper-intake-stack';
test('paper-intake runtime role can read only its retained secret and trusts the production app',()=>{
 const app=new cdk.App();const template=Template.fromStack(new FrontendPaperIntakeStack(app,'Intake',{env:{account:'395567831870',region:'us-east-1'}}));
 template.resourceCountIs('AWS::Amplify::App',0);template.resourceCountIs('AWS::Amplify::Branch',0);
 template.hasResourceProperties('AWS::SecretsManager::Secret',{Name:'jumpserve/frontend/paper-intake'});
 template.hasResourceProperties('AWS::IAM::Role',{RoleName:'JumpServeFrontendPaperIntake',AssumeRolePolicyDocument:{Statement:Match.arrayWith([Match.objectLike({Principal:{Service:'amplify.amazonaws.com'},Condition:{StringEquals:{'aws:SourceAccount':'395567831870'},ArnLike:{'aws:SourceArn':[{'Fn::Join':['',['arn:',{Ref:'AWS::Partition'},':amplify:us-east-1:395567831870:apps/d24jvguj7brnkj']]},{'Fn::Join':['',['arn:',{Ref:'AWS::Partition'},':amplify:us-east-1:395567831870:apps/d24jvguj7brnkj/branches/main']]}]}}})])}});
 const policies=Object.values(template.findResources('AWS::IAM::Policy'));
 expect(policies).toHaveLength(1);expect(policies[0].Properties.PolicyDocument.Statement).toHaveLength(1);expect(policies[0].Properties.PolicyDocument.Statement[0]).toMatchObject({Action:'secretsmanager:GetSecretValue',Effect:'Allow'});expect(policies[0].Properties.PolicyDocument.Statement[0].Resource).toHaveProperty('Ref');
 const secret=Object.values(template.findResources('AWS::SecretsManager::Secret'))[0];expect(secret.DeletionPolicy).toBe('Retain');
 expect(secret.Properties.SecretString).toBeUndefined();expect(JSON.stringify(template.toJSON())).not.toMatch(/sk-proj-|sb_secret_/);
});
