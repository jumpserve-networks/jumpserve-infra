import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as secrets from 'aws-cdk-lib/aws-secretsmanager';
import {Template,Match} from 'aws-cdk-lib/assertions';
import {IntakeWorker} from '../lib/intake-worker';

test('intake uses separate encrypted compute; original refresh owner is imported and never replaced',()=>{
 const app=new cdk.App();
 const stack=new cdk.Stack(app,'IntakeOnly',{env:{account:'395567831870',region:'us-east-1'}});
 const vpc=new ec2.Vpc(stack,'FixtureVpc',{natGateways:0,maxAzs:1});
 new IntakeWorker(stack,'Intake',{vpc,ownerRoleArn:'arn:aws:iam::395567831870:role/JumpServeOpenClawStack-WorkerRoleAAEB1603-AMhySy8UAI7S',
  secret:secrets.Secret.fromSecretNameV2(stack,'ExistingServiceKey','jumpserve/supabase-service-key')});
 const template=Template.fromStack(stack);
 template.resourceCountIs('AWS::EC2::Instance',1);template.resourceCountIs('AWS::IAM::Role',1);
 template.hasResourceProperties('AWS::EC2::LaunchTemplate',{LaunchTemplateData:{MetadataOptions:{HttpTokens:'required'}}});
 template.hasResourceProperties('AWS::EC2::Instance',{InstanceType:'t3.large',
  BlockDeviceMappings:Match.arrayWith([{DeviceName:'/dev/xvda',Ebs:{VolumeSize:32,VolumeType:'gp3',Encrypted:true,DeleteOnTermination:false}}])});
 const groups=template.findResources('AWS::EC2::SecurityGroup');
 const intake=Object.values(groups).find(x=>x.Properties.GroupDescription.startsWith('Dedicated intake'));
 expect(intake).toBeDefined();expect(intake!.Properties.SecurityGroupIngress).toBeUndefined();
 const policies=JSON.stringify(template.findResources('AWS::IAM::Policy'));
 expect(policies).toContain('ssm:PutParameter');expect(policies).toContain('ssm:GetParameter');expect(policies).toContain('NotResource');
 expect(policies).not.toContain('iam:PassRole');
 const release=Object.values(template.findResources('AWS::IAM::Policy')).find(x=>x.Properties.Roles?.includes('JumpServePlatformRelease'));
 expect(release).toBeDefined();
 const command=release!.Properties.PolicyDocument.Statement.find((x:{Action:string|string[]})=>x.Action==='ssm:SendCommand'||Array.isArray(x.Action)&&x.Action.includes('ssm:SendCommand'));
 const host=Object.keys(template.findResources('AWS::EC2::Instance'))[0];
 expect(command.Resource).toHaveLength(2);
 expect(command.Resource).toEqual(expect.arrayContaining(['arn:aws:ssm:us-east-1::document/AWS-RunShellScript',
  {'Fn::Join':['',['arn:',{Ref:'AWS::Partition'},':ec2:us-east-1:395567831870:instance/',{Ref:host}]]}]));
 expect(JSON.stringify(release)).not.toContain('instance/*');
 const resources=JSON.stringify(template.toJSON());
 expect(resources).not.toContain('refresh_token');expect(resources).not.toContain('JumpServeOpenClawStack/Worker');
 expect(resources).toContain('intake-runtime');expect(resources).toContain('jumpserve-intake.service');
});
