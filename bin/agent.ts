#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { AgentStack } from '../lib/agent-stack';

// Keep agent-only releases independent of benchmark runtime assets and lookups.
const app = new cdk.App();
new AgentStack(app, 'JumpServeAgentStack', {
  env: { account: '395567831870', region: 'us-east-1' },
});
