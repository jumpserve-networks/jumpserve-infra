#!/usr/bin/env node
// Standalone entry point: benchmark updates do not require the agent layer or
// synthesize the Amplify and long-lived EC2 stacks.
import * as cdk from 'aws-cdk-lib/core';
import { BenchmarkOrchestratorStack } from '../lib/benchmark-orchestrator-stack';

const app = new cdk.App();
new BenchmarkOrchestratorStack(app, 'JumpServeBenchmarkStack', {
  env: { account: '395567831870', region: 'us-east-1' },
});
