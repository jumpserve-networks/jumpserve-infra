#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { AmplifyStack } from '../lib/amplify-stack';
import { Ec2Stack } from '../lib/ec2-stack';

const app = new cdk.App();

const env = {
  account: '395567831870',
  region: 'us-east-1',
};

new AmplifyStack(app, 'JumpServeAmplifyStack', { env });
new Ec2Stack(app, 'JumpServeEc2Stack', { env });
