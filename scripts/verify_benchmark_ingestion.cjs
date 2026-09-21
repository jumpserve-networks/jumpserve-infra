#!/usr/bin/env node
// Fixed live verification: one small two-client test, safe metadata only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const root = path.resolve(__dirname, '..');
const checkpoint = path.join(root, '.test-artifacts/ingestion-live-verification.json');
const launcher = 'JumpServeBenchmarkStack-LaunchBenchmarkFn5833EFAD-L6HWyzv2tgwl';
const aws = (service, operation, ...args) => JSON.parse(execFileSync('aws', [service, operation, ...args,
  '--region', 'us-east-1', '--output', 'json'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }));
async function main() {
  const action = process.argv[2];
  assert.ok(['launch', 'check', 'cleanup'].includes(action));
  assert.equal(aws('sts', 'get-caller-identity').Account, '395567831870');
  const configuration = aws('lambda', 'get-function-configuration', '--function-name', launcher);
  Object.assign(process.env, configuration.Environment.Variables, { AWS_REGION: 'us-east-1' });
  assert.equal(process.env.BENCHMARK_INGEST_URL, 'https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/benchmarks/ingest');
  if (action === 'launch') {
    assert.ok(!fs.existsSync(checkpoint), 'A verification job already exists; check it before launching another.');
    const { handler } = require('../lambda/launch-benchmark/index.js');
    const response = await handler({ source: 'jumpserve.ami-verification', body: JSON.stringify({ config: {
      num_clients: 2, client_delays_ms: [10, 20], client_ccas: ['cubic', 'cubic'],
      client_file_sizes_mbytes: [1, 1], client_start_delays_ms: [0, 0],
      bottleneck_all_client_rate_mbit: 10, bottleneck_buffer_kbytes: 125,
      snapshot_metrics_source: 'kernel', snapshot_interval_ms: 100,
      script: 'netem_cubic_benchmark_nines.py', experiment_name: 'security-ingestion-verification',
      tags: ['verification'], notes: 'Operational ingestion and automatic termination check; exclude from research cohorts.',
    } }) });
    assert.equal(response.statusCode, 200, 'Verification launcher failed');
    const job = JSON.parse(response.body);
    fs.writeFileSync(checkpoint, JSON.stringify(job, null, 2)+'\n');
    console.log(JSON.stringify(job));
    return;
  }
  const job = JSON.parse(fs.readFileSync(checkpoint));
  const instance = aws('ec2', 'describe-instances', '--instance-ids', job.instanceId).Reservations[0].Instances[0];
  assert.ok(instance.Tags.some(tag => tag.Key === 'BenchmarkJobId' && tag.Value === job.jobId));
  if (action === 'cleanup') {
    if (instance.State.Name !== 'terminated') aws('ec2', 'terminate-instances', '--instance-ids', job.instanceId);
    console.log('Verification instance cleanup requested.');
    return;
  }
  // Inspect user data without printing or persisting its job capability.
  if (instance.State.Name !== 'terminated') {
    const encoded = aws('ec2', 'describe-instance-attribute', '--instance-id', job.instanceId, '--attribute', 'userData').UserData.Value;
    const bootstrap = Buffer.from(encoded, 'base64').toString();
    assert.ok(!/supabase\.co|supabase-service-role-key|sb_secret_|eyJ[\w-]+\.[\w-]+\.[\w-]+/.test(bootstrap));
    assert.ok(bootstrap.includes('JUMPSERVE_JOB_TOKEN'));
  }
  const { SecretString: key } = aws('secretsmanager', 'get-secret-value', '--secret-id', process.env.SUPABASE_SECRET_ARN);
  const response = await fetch(`${process.env.SUPABASE_URL}/rest/v1/benchmark_jobs?id=eq.${job.jobId}&select=status,parent_run_id`, { headers: { apikey: key } });
  assert.ok(response.ok, 'Job read failed');
  const [record] = await response.json();
  const result = { ...job, ...record, instanceState: instance.State.Name };
  if (record.status === 'completed') {
    assert.ok(record.parent_run_id);
    const runs = await fetch(`${process.env.SUPABASE_URL}/rest/v1/emulated_runs?emulated_parent_run_id=eq.${record.parent_run_id}&select=id`, { headers: { apikey: key } });
    const rows = await runs.json();
    assert.equal(rows.length, 2);
    const stats = await fetch(`${process.env.SUPABASE_URL}/rest/v1/emulated_snapshot_stats?emulated_run_id=in.(${rows.map(row => row.id).join(',')})&select=id&limit=1`, { headers: { apikey: key } });
    assert.ok((await stats.json()).length > 0, 'No measurement samples saved');
    result.measurementsVerified = true;
  }
  fs.writeFileSync(checkpoint, JSON.stringify(result, null, 2)+'\n');
  console.log(JSON.stringify(result));
}
main().catch(error => { console.error(error.name + ': ' + error.message); process.exitCode = 1; });
