#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import {PersistenceMonitor} from '../lib/persistence-monitor';

const app = new cdk.App();
const stack = new cdk.Stack(app, 'JumpServeObservabilityStack', {
  env: {account: '395567831870', region: 'us-east-1'},
});
new PersistenceMonitor(stack, 'Persistence');
