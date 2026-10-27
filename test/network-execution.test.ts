import * as cdk from 'aws-cdk-lib';
import * as api from 'aws-cdk-lib/aws-apigatewayv2';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import { Template, Match } from 'aws-cdk-lib/assertions';
import { ResearchWorkflow } from '../lib/research-workflow';
import { networkEnvelope } from '../lambda/shared/research-network';

test('API Gateway bodies cannot select the private IAM networking envelope',()=>{
 const body={source:'jumpserve.network-execution',job_id:'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',action:'launch'};
 expect(networkEnvelope(body)).toEqual(body);
 expect(networkEnvelope({...body,requestContext:{http:{method:'POST'}}})).toBeNull();
 expect(()=>networkEnvelope({...body,owner_id:'forged'})).toThrow();
 expect(()=>networkEnvelope({...body,action:'execute-shell'})).toThrow();
});
test('network workers invoke only registered functions; custom hosts receive no IAM profile',()=>{
 const app=new cdk.App({context:{supabaseUrl:'https://regphejnlvfpyokpniny.supabase.co',researchQueueEnabled:true,networkExecutionEnabled:true,networkPackagesEnabled:true}});
 const stack=new cdk.Stack(app,'NetworkExecution',{env:{account:'395567831870',region:'us-east-1'}});
 const vpc=new ec2.Vpc(stack,'ExistingVpc',{natGateways:0,maxAzs:1});
 const emulated=new lambda.Function(stack,'Emulated',{runtime:lambda.Runtime.NODEJS_22_X,handler:'index.handler',code:lambda.Code.fromInline('exports.handler=async()=>({});')});
 const realWorld=new lambda.Function(stack,'RealWorld',{runtime:lambda.Runtime.PYTHON_3_12,handler:'index.handler',code:lambda.Code.fromInline('def handler(event,context): return {}')});
 new ResearchWorkflow(stack,'Research',new api.HttpApi(stack,'Api'),{emulated,realWorld,vpc});
 const t=Template.fromStack(stack);
 t.hasResourceProperties('AWS::Lambda::Function',{Handler:'network_package.handler',Timeout:60,Environment:{Variables:Match.objectLike({NETWORK_PACKAGE_AMI:'ami-02a9cdd4e98bc3c78'})}});
 expect(JSON.stringify(t.toJSON().Parameters)).not.toContain('/ubuntu/server/24.04/stable/current/');
 t.hasResourceProperties('AWS::Lambda::Function',{Handler:'network_package.reap',Timeout:120});
 t.hasResourceProperties('AWS::Lambda::Function',{Handler:'network_package.ingest',Timeout:29});
 t.hasResourceProperties('AWS::ApiGatewayV2::Route',{RouteKey:'POST /research/studies/{studyId}/network'});
 t.hasResourceProperties('AWS::ApiGatewayV2::Route',{RouteKey:'POST /research/network-ingest'});
 t.hasResourceProperties('AWS::Lambda::Function',{Handler:'worker.handler',Environment:{Variables:Match.objectLike({NETWORK_EMULATED_FUNCTION:Match.anyValue(),NETWORK_REAL_WORLD_FUNCTION:Match.anyValue(),NETWORK_PACKAGE_FUNCTION:Match.anyValue()})}});
 t.resourceCountIs('AWS::EC2::Instance',0);t.resourceCountIs('AWS::IAM::InstanceProfile',0);
 const policies=JSON.stringify(t.findResources('AWS::IAM::Policy'));
 expect(policies).toContain('lambda:InvokeFunction');expect(policies).toContain('ec2:ResourceTag/Project');
 expect(policies).not.toContain('iam:PassRole');expect(policies).not.toContain('bedrock:');
});
test('custom package queue admission is disabled until operational checks pass',()=>{
 const app=new cdk.App({context:{supabaseUrl:'https://regphejnlvfpyokpniny.supabase.co',researchQueueEnabled:true,networkExecutionEnabled:true}});
 const stack=new cdk.Stack(app,'PackageAdmission',{env:{account:'395567831870',region:'us-east-1'}});
 const vpc=new ec2.Vpc(stack,'ExistingVpc',{natGateways:0,maxAzs:1});
 const emulated=new lambda.Function(stack,'Emulated',{runtime:lambda.Runtime.NODEJS_22_X,handler:'index.handler',code:lambda.Code.fromInline('exports.handler=async()=>({});')});
 const realWorld=new lambda.Function(stack,'RealWorld',{runtime:lambda.Runtime.PYTHON_3_12,handler:'index.handler',code:lambda.Code.fromInline('def handler(event,context): return {}')});
 new ResearchWorkflow(stack,'Research',new api.HttpApi(stack,'Api'),{emulated,realWorld,vpc});
 const t=Template.fromStack(stack);
 t.hasResourceProperties('AWS::Lambda::Function',{Handler:'network_package.handler'});
 const services=t.findResources('AWS::Lambda::Function');
 for(const service of Object.values(services)){
  const props=service.Properties;
  if(props.Handler==='api.handler'||props.Handler==='worker.handler'){
   expect(props.Environment.Variables.NETWORK_PACKAGE_FUNCTION).toBeUndefined();
  if (props.Handler === 'worker.handler' || props.Handler === 'api.handler') {
   expect(props.Environment.Variables.NETWORK_NETEM_IPERF_FUNCTION).toBeDefined();
   expect(props.Environment.Variables.NETWORK_NETEM_IPERF_POLICY_SHA256).toMatch(/^[a-f0-9]{64}$/);
  }
   expect(props.Environment.Variables.NETWORK_EMULATED_FUNCTION).toBeDefined();
   expect(props.Environment.Variables.NETWORK_REAL_WORLD_FUNCTION).toBeDefined();
  }
 }
});
test('native experiment builder fails closed without its native worker and disposable executor',()=>{
 const app=new cdk.App({context:{supabaseUrl:'https://regphejnlvfpyokpniny.supabase.co',researchQueueEnabled:true,researchAutonomyEnabled:true,researchExperimentBuilderEnabled:true}});
 const stack=new cdk.Stack(app,'InvalidBuilder',{env:{account:'395567831870',region:'us-east-1'}});
 expect(()=>new ResearchWorkflow(stack,'Research',new api.HttpApi(stack,'Api'))).toThrow('Experiment builder requires native OpenClaw');
});
test('generated packages use a separately pinned executor and keep arbitrary custom package admission disabled',()=>{
 const app=new cdk.App({context:{supabaseUrl:'https://regphejnlvfpyokpniny.supabase.co',researchQueueEnabled:true,researchAutonomyEnabled:true,researchOpenClawEnabled:true,networkExecutionEnabled:true,researchExperimentBuilderEnabled:true}});
 const stack=new cdk.Stack(app,'GeneratedPackages',{env:{account:'395567831870',region:'us-east-1'}});
 const vpc=new ec2.Vpc(stack,'ExistingVpc',{natGateways:0,maxAzs:1});
 const emulated=new lambda.Function(stack,'Emulated',{runtime:lambda.Runtime.NODEJS_22_X,handler:'index.handler',code:lambda.Code.fromInline('exports.handler=async()=>({});')});
 const realWorld=new lambda.Function(stack,'RealWorld',{runtime:lambda.Runtime.PYTHON_3_12,handler:'index.handler',code:lambda.Code.fromInline('def handler(event,context): return {}')});
 new ResearchWorkflow(stack,'Research',new api.HttpApi(stack,'Api'),{emulated,realWorld,vpc});
 const t=Template.fromStack(stack);const functions=t.findResources('AWS::Lambda::Function');
 for(const item of Object.values(functions)){
  const props=item.Properties;
  if(['api.handler','worker.handler','autonomy.handler'].includes(props.Handler)){
   expect(props.Environment.Variables.NETWORK_BUILT_PACKAGE_FUNCTION).toBeDefined();
   expect(props.Environment.Variables.NETWORK_BUILT_PACKAGE_POLICY_SHA256).toMatch(/^[a-f0-9]{64}$/);
   expect(props.Environment.Variables.NETWORK_PACKAGE_FUNCTION).toBeUndefined();
  }
 }
 t.resourceCountIs('AWS::EC2::Instance',0);expect(JSON.stringify(t.findResources('AWS::IAM::Policy'))).not.toContain('iam:PassRole');
});
