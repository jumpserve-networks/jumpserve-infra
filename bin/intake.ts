#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as secrets from 'aws-cdk-lib/aws-secretsmanager';
import {IntakeWorker} from '../lib/intake-worker';
const app=new cdk.App();
const stack=new cdk.Stack(app,'JumpServeIntakeStack',{env:{account:'395567831870',region:'us-east-1'}});
new IntakeWorker(stack,'Intake',{vpc:ec2.Vpc.fromLookup(stack,'DefaultVpc',{isDefault:true}),
 ownerRoleArn:'arn:aws:iam::395567831870:role/JumpServeOpenClawStack-WorkerRoleAAEB1603-AMhySy8UAI7S',
 secret:secrets.Secret.fromSecretNameV2(stack,'SupabaseServiceKey','jumpserve/supabase-service-key')});
