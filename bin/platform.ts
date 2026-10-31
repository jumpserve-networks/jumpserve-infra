#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib/core';
import { PlatformSupervisorAccess } from '../lib/platform-supervisor-access';
const app = new cdk.App();
const stack = new cdk.Stack(app, 'JumpServePlatformAccessStack', { env: { account: '395567831870', region: 'us-east-1' } });
new PlatformSupervisorAccess(stack, 'Access', {
  workerRoleName: app.node.tryGetContext('platformWorkerRoleName') || '',
  assetBucketName: app.node.tryGetContext('platformAssetBucketName') || '',
  apiIds: String(app.node.tryGetContext('platformApiIds') || '').split(',').filter(Boolean),
});
