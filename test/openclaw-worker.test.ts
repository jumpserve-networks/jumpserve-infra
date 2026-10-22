import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as secrets from 'aws-cdk-lib/aws-secretsmanager';
import {Template} from 'aws-cdk-lib/assertions';
import {OpenClawWorker} from '../lib/openclaw-worker';
import * as path from 'path';
test('private OpenClaw worker has no ingress, no model billing fallback permission, encrypted retained state and SSM access',()=>{
 const app=new cdk.App();const stack=new cdk.Stack(app,'PrivateOpenClaw',{env:{account:'395567831870',region:'us-east-1'}});
 const vpc=new ec2.Vpc(stack,'Network',{maxAzs:1,natGateways:0});
 new OpenClawWorker(stack,'Worker',{vpc,runtime:path.join(__dirname,'..','.runtime-backend','research_workflow'),secret:secrets.Secret.fromSecretNameV2(stack,'Key','jumpserve/supabase-service-key')});
 const t=Template.fromStack(stack);t.hasResourceProperties('AWS::EC2::Instance',{ImageId:'ami-0636d90d6337ae368',InstanceType:'t3.medium',BlockDeviceMappings:[{DeviceName:'/dev/xvda',Ebs:{VolumeSize:24,Encrypted:true,DeleteOnTermination:false,VolumeType:'gp3'}}]});
 for(const r of Object.values(t.findResources('AWS::EC2::SecurityGroup')))expect(r.Properties.SecurityGroupIngress??[]).toEqual([]);
 const policies=JSON.stringify(t.findResources('AWS::IAM::Policy'));expect(policies).toContain('secretsmanager:GetSecretValue');
 for(const permission of ['bedrock:','ec2:RunInstances','lambda:InvokeFunction'])expect(policies).not.toContain(permission);
});
