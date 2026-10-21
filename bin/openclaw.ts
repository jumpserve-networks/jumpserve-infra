#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as secrets from 'aws-cdk-lib/aws-secretsmanager';
import {OpenClawWorker} from '../lib/openclaw-worker';
import * as path from 'path';
const app=new cdk.App();
const stack=new cdk.Stack(app,'JumpServeOpenClawStack',{env:{account:'395567831870',region:'us-east-1'}});
if(stack.node.tryGetContext('supabaseUrl')!=='https://regphejnlvfpyokpniny.supabase.co')throw new Error('Verified JumpServe project required.');
new OpenClawWorker(stack,'Worker',{vpc:ec2.Vpc.fromLookup(stack,'DefaultVpc',{isDefault:true}),runtime:path.join(__dirname,'..','.runtime-backend','research_workflow'),secret:secrets.Secret.fromSecretNameV2(stack,'SupabaseServiceKey','jumpserve/supabase-service-key')});
