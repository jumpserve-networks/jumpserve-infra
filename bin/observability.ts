#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import {PersistenceMonitor} from '../lib/persistence-monitor';

const app = new cdk.App();
if (app.node.tryGetContext('cloudBenchmarksRetired') === true) {
  throw new Error('The custom database monitoring stack is retired by owner instruction.');
}
const stack = new cdk.Stack(app, 'JumpServeObservabilityStack', {
  env: {account: '395567831870', region: 'us-east-1'},
});
new PersistenceMonitor(stack, 'Persistence');
