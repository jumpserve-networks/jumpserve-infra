#!/usr/bin/env node
// Launch two small, real jobs through the candidate handler, without changing
// the live Lambda. All AWS and Supabase credentials remain in process memory.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const { setTimeout: delay } = require('node:timers/promises');
assert.ok(process.argv.slice(2).every(argument => argument === '--live-launcher'), 'Only --live-launcher is supported');
const liveLauncher = process.argv.includes('--live-launcher');

const manifest = JSON.parse(fs.readFileSync('cdk.out/benchmark-ami.json', 'utf8'));
const profile = process.env.AWS_PROFILE;
const region = manifest.region;
const aws = (...args) => JSON.parse(execFileSync('aws', [
  ...(profile ? ['--profile', profile] : []), '--region', region, '--no-cli-pager', '--output', 'json', ...args,
], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }));

async function main() {
  assert.equal(aws('sts', 'get-caller-identity').Account, '395567831870');
  const image = aws('ec2', 'describe-images', '--image-ids', manifest.ami_id).Images[0];
  assert.equal(image.OwnerId, '395567831870');
  assert.equal(image.State, 'available');
  assert.ok(image.Tags.some(tag => tag.Key === 'Purpose' && tag.Value === 'BenchmarkAMI'));
  assert.ok(image.Tags.some(tag => tag.Key === 'BackendCommit' && tag.Value === manifest.backend_commit));

  const configuration = aws('lambda', 'get-function-configuration', '--function-name',
    'JumpServeBenchmarkStack-LaunchBenchmarkFn5833EFAD-L6HWyzv2tgwl');
  if (liveLauncher) {
    assert.equal(configuration.Environment.Variables.AMI_ID, manifest.ami_id);
    assert.equal(configuration.Environment.Variables.BENCHMARK_IMAGE_MODE, 'prebaked');
  }
  Object.assign(process.env, configuration.Environment.Variables, {
    AWS_REGION: region,
    AMI_ID: manifest.ami_id, BENCHMARK_IMAGE_MODE: 'prebaked',
  });
  const { handler } = require('../lambda/launch-benchmark/index.js');
  const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
  const secret = await new SecretsManagerClient({}).send(new GetSecretValueCommand({
    SecretId: process.env.SUPABASE_SECRET_ARN,
  }));
  const headers = { apikey: secret.SecretString, Authorization: `Bearer ${secret.SecretString}` };
  const reports = [];
  for (const expectedStatus of (liveLauncher ? ['completed'] : ['completed', 'failed'])) {
    const config = {
      num_clients: 2, client_delays_ms: [10, 20], client_ccas: ['cubic', 'cubic'],
      client_file_sizes_mbytes: [5, 5], client_start_delays_ms: [0, 0],
      bottleneck_all_client_rate_mbit: 10, bottleneck_buffer_kbytes: 125,
      snapshot_metrics_source: expectedStatus === 'failed' ? 'invalid-ami-verification' : 'kernel',
      script: 'netem_cubic_benchmark_nines.py', experiment_name: `ami-verification-${expectedStatus}`,
    };
    const start = Date.now();
    const body = JSON.stringify({ config });
    const invocation = { source: 'jumpserve.ami-verification', body };
    let response;
    if (liveLauncher) {
      const responseFile = 'cdk.out/ami-launcher-response.json';
      try {
        const result = aws('lambda', 'invoke', '--function-name', configuration.FunctionArn,
          '--cli-binary-format', 'raw-in-base64-out', '--payload', JSON.stringify(invocation), responseFile);
        assert.ok(!result.FunctionError, 'Deployed launcher invocation failed');
        response = JSON.parse(fs.readFileSync(responseFile, 'utf8'));
      } finally {
        if (fs.existsSync(responseFile)) fs.unlinkSync(responseFile);
      }
    } else {
      response = await handler(invocation);
    }
    assert.equal(response.statusCode, 200, 'Candidate launcher failed');
    const job = JSON.parse(response.body);
    // Safe identifiers only; never persist credentials, user data or raw logs.
    const checkpoint = 'cdk.out/benchmark-ami-verification-instances.json';
    const launched = fs.existsSync(checkpoint) ? JSON.parse(fs.readFileSync(checkpoint, 'utf8')) : [];
    launched.push({ jobId: job.jobId, instanceId: job.instanceId, amiId: manifest.ami_id });
    fs.writeFileSync(checkpoint, JSON.stringify(launched, null, 2) + '\n');
    console.log(JSON.stringify({ expectedStatus, ...job, amiId: manifest.ami_id }));
    let terminal = false;
    try {
      for (let attempt = 0; attempt < 60; attempt++) {
        const instance = aws('ec2', 'describe-instances', '--instance-ids', job.instanceId).Reservations[0].Instances[0];
        if (instance.State.Name === 'terminated') { terminal = true; break; }
        await delay(10000);
      }
      assert.ok(terminal, 'Instance did not automatically terminate within 10 minutes');
      const result = await fetch(`${process.env.SUPABASE_URL}/rest/v1/benchmark_jobs?id=eq.${job.jobId}&select=id,status,parent_run_id,error_message,created_at,updated_at`, { headers });
      assert.ok(result.ok, 'Unable to read the verification job');
      const [row] = await result.json();
      assert.equal(row.status, expectedStatus);
      if (expectedStatus === 'completed') assert.ok(row.parent_run_id, 'Successful run did not save a parent result');
      else assert.match(row.error_message, /Benchmark failed during running \(exit 2\)/);
      const events = aws('logs', 'get-log-events', '--log-group-name', '/jumpserve/benchmark',
        '--log-stream-name', job.jobId, '--start-from-head', '--limit', '10000').events;
      const output = events.map(event => event.message).join('\n');
      assert.ok(output.includes(`Benchmark image backend commit: ${manifest.backend_commit}`), 'Fresh user data did not verify the baked backend');
      assert.ok(!/Unpacking |Preparing to unpack |apt-get|git clone|git pull/.test(output), 'Software installation occurred during benchmark startup');
      assert.ok(!output.includes(secret.SecretString), 'Credential found in benchmark logs');
      const report = { amiId: manifest.ami_id, backendCommit: manifest.backend_commit,
        jobId: job.jobId, instanceId: job.instanceId, status: row.status,
        parentRunId: row.parent_run_id, totalSeconds: Math.round((Date.now() - start) / 1000),
        createdAt: row.created_at, updatedAt: row.updated_at, logEvents: events.length };
      reports.push(report);
      console.log(JSON.stringify(report));
    } finally {
      if (!terminal) {
        aws('ec2', 'terminate-instances', '--instance-ids', job.instanceId);
        console.log(`Cleanup requested for verification instance ${job.instanceId}`);
      }
    }
  }
  fs.writeFileSync(`cdk.out/benchmark-ami${liveLauncher ? '-live' : ''}-verification.json`, JSON.stringify(reports, null, 2) + '\n');
}

main().catch(error => {
  // Never dump SDK request objects, environment variables or secret values.
  console.error(`${error.name}: ${error.message}`);
  process.exitCode = 1;
});
