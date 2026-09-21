import { AuthError, requireUser } from '../shared/auth';
import { randomBytes, createHash } from 'node:crypto';
import { buildUserData, type BenchmarkConfig } from './user-data';
import {
  EC2Client,
  RunInstancesCommand,
  CreateTagsCommand,
} from '@aws-sdk/client-ec2';
import {
  SecretsManagerClient,
  GetSecretValueCommand,
} from '@aws-sdk/client-secrets-manager';

const ec2 = new EC2Client({});
const sm = new SecretsManagerClient({});

const ALLOWED_CCAS = ['cubic', 'bbr', 'bbr2', 'bbr3', 'reno', 'vegas', 'htcp', 'highspeed', 'scalable', 'westwood'];
const ALLOWED_SCRIPTS = ['netem_cubic_benchmark_hotnets.py', 'netem_cubic_benchmark_nines.py', 'netem_nines.py', 'netem_multi_bottleneck.py'];

function validateConfig(config: BenchmarkConfig): string | null {
  const inRange = (value: unknown, min: number, max: number): boolean =>
    typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
  if (!Number.isInteger(config.num_clients) || !inRange(config.num_clients, 1, 10)) {
    return 'num_clients must be between 1 and 10';
  }
  if (!Array.isArray(config.client_delays_ms) || config.client_delays_ms.length !== config.num_clients) {
    return 'client_delays_ms must match num_clients';
  }
  if (!Array.isArray(config.client_ccas) || config.client_ccas.length !== config.num_clients) {
    return 'client_ccas must match num_clients';
  }
  for (const cca of config.client_ccas) {
    if (!ALLOWED_CCAS.includes(cca)) {
      return `Invalid CCA: ${cca}. Allowed: ${ALLOWED_CCAS.join(', ')}`;
    }
  }
  if (!Array.isArray(config.client_file_sizes_mbytes) || config.client_file_sizes_mbytes.length !== config.num_clients) {
    return 'client_file_sizes_mbytes must match num_clients';
  }
  for (const d of config.client_delays_ms) {
    if (!inRange(d, 0, 5000)) return 'client_delays_ms values must be numbers from 0-5000';
  }
  for (const s of config.client_file_sizes_mbytes) {
    if (!inRange(s, 0.1, 1000)) return 'client_file_sizes_mbytes values must be numbers from 0.1-1000';
  }
  if (config.client_start_delays_ms !== undefined && (
    !Array.isArray(config.client_start_delays_ms) ||
    config.client_start_delays_ms.length !== config.num_clients ||
    !config.client_start_delays_ms.every((delay) => inRange(delay, 0, 600000))
  )) return 'client_start_delays_ms must contain one number from 0-600000 per client';
  if (config.loss_pct !== undefined && !inRange(config.loss_pct, 0, 100)) {
    return 'loss_pct must be a number from 0-100';
  }
  if (config.snapshot_interval_ms !== undefined && (
    !Number.isInteger(config.snapshot_interval_ms) || !inRange(config.snapshot_interval_ms, 1, 60000)
  )) return 'snapshot_interval_ms must be an integer from 1-60000';
  if (config.script === 'netem_multi_bottleneck.py') {
    if (!['parking-lot', 'dumbbell'].includes(config.topology!)) {
      return 'Choose a topology for the multi-bottleneck benchmark: parking-lot or dumbbell';
    }
    if (!Array.isArray(config.bottleneck_rates_mbit) || config.bottleneck_rates_mbit.length !== 2 ||
        !config.bottleneck_rates_mbit.every((rate) => inRange(rate, 1, 10000))) {
      return 'bottleneck_rates_mbit must contain exactly two numbers from 1-10000';
    }
    if (!Array.isArray(config.bottleneck_buffers_kbytes) || config.bottleneck_buffers_kbytes.length !== 2 ||
        !config.bottleneck_buffers_kbytes.every((buffer) => inRange(buffer, 0, 100000))) {
      return 'bottleneck_buffers_kbytes must contain exactly two numbers from 0-100000';
    }
    if (config.topology === 'dumbbell' && (
      !Array.isArray(config.client_groups) || config.client_groups.length !== 2 ||
      !config.client_groups.every((size) => Number.isInteger(size) && size > 0) ||
      config.client_groups.reduce((sum, size) => sum + size, 0) !== config.num_clients
    )) return 'client_groups must contain two positive group sizes adding up to num_clients';
  } else {
    if (!inRange(config.bottleneck_all_client_rate_mbit, 1, 10000)) {
      return 'bottleneck_all_client_rate_mbit must be 1-10000';
    }
    if (!inRange(config.bottleneck_buffer_kbytes, 0, 100000)) {
      return 'bottleneck_buffer_kbytes must be 0-100000';
    }
    if (config.snapshot_metrics_source && !['kernel', 'ss'].includes(config.snapshot_metrics_source)) {
      return 'snapshot_metrics_source must be kernel or ss';
    }
  }
  if (config.script && !ALLOWED_SCRIPTS.includes(config.script)) {
    return `Invalid script: ${config.script}. Allowed: ${ALLOWED_SCRIPTS.join(', ')}`;
  }
  return null;
}

async function supabaseRequest(method: string, path: string, body?: object, apiKey?: string): Promise<any> {
  const supabaseUrl = process.env.SUPABASE_URL!;
  const key = apiKey || process.env.SUPABASE_SERVICE_KEY!;
  const url = `${supabaseUrl}/rest/v1/${path}`;

  const headers: Record<string, string> = {
    'apikey': key,
    'Content-Type': 'application/json',
    'Prefer': method === 'POST' ? 'return=representation' : 'return=minimal',
  };

  const response = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Supabase ${method} ${path} failed: ${response.status} ${text}`);
  }

  if (method === 'POST' || (method === 'GET')) {
    return response.json();
  }
  return null;
}

export const handler = async (event: any) => {
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
    'Access-Control-Allow-Methods': 'POST,OPTIONS',
  };

  if (event.requestContext?.http?.method === 'OPTIONS') {
    return { statusCode: 200, headers: corsHeaders, body: '' };
  }

  try {
    // This function has no Function URL. API Gateway always supplies requestContext;
    // the exact operator envelope below is reachable only through IAM-authorized
    // Lambda Invoke (or locally, where AWS credentials authorize privileged calls).
    const operatorVerification = event.source === 'jumpserve.ami-verification' &&
      Object.keys(event).every((key) => key === 'source' || key === 'body');
    const user = operatorVerification
      ? { id: 'jumpserve-ami-verification', email: undefined }
      : await requireUser(event);
    const body = JSON.parse(event.body || '{}');
    const config: BenchmarkConfig = body.config;
    const requestedBy = user.email || user.id;

    if (!config) {
      return {
        statusCode: 400,
        headers: corsHeaders,
        body: JSON.stringify({ error: 'config is required' }),
      };
    }

    const validationError = validateConfig(config);
    if (validationError) {
      return {
        statusCode: 400,
        headers: corsHeaders,
        body: JSON.stringify({ error: validationError }),
      };
    }

    // Get Supabase service key from Secrets Manager
    const secretResp = await sm.send(new GetSecretValueCommand({
      SecretId: process.env.SUPABASE_SECRET_ARN!,
    }));
    const supabaseKey = secretResp.SecretString!;

    // Check concurrent running jobs
    const runningJobs = await supabaseRequest(
      'GET',
      'benchmark_jobs?status=in.(pending,launching,installing,cloning,running)&select=id',
      undefined,
      supabaseKey,
    );
    if (runningJobs.length >= 5) {
      return {
        statusCode: 429,
        headers: corsHeaders,
        body: JSON.stringify({ error: 'Maximum 5 concurrent benchmark jobs. Please wait for existing jobs to complete.' }),
      };
    }

    // Insert job row
    const [job] = await supabaseRequest('POST', 'benchmark_jobs', {
      status: 'launching',
      config,
      requested_by: requestedBy,
    }, supabaseKey);

    const jobId = job.id;

    // Store only the token hash. The runner can submit exactly this job's report.
    const jobToken = randomBytes(32).toString('hex');
    await supabaseRequest('POST', 'benchmark_ingest_tokens', {
      job_id: jobId,
      token_hash: createHash('sha256').update(jobToken).digest('hex'),
    }, supabaseKey);
    const userData = buildUserData(config, jobId, jobToken);

    const runResult = await ec2.send(new RunInstancesCommand({
      ImageId: process.env.AMI_ID!,
      InstanceType: 't3.medium',
      InstanceInitiatedShutdownBehavior: 'terminate',
      MetadataOptions: { HttpTokens: 'required', HttpEndpoint: 'enabled' },
      MinCount: 1,
      MaxCount: 1,
      UserData: userData,
      SecurityGroupIds: [process.env.SECURITY_GROUP_ID!],
      SubnetId: process.env.SUBNET_ID!,
      IamInstanceProfile: {
        Arn: process.env.INSTANCE_PROFILE_ARN!,
      },
      TagSpecifications: [{
        ResourceType: 'instance',
        Tags: [
          { Key: 'Name', Value: `JumpServe-Benchmark-${jobId.slice(0, 8)}` },
          { Key: 'BenchmarkJobId', Value: jobId },
          { Key: 'Project', Value: 'JumpServe' },
        ],
      }],
    }));

    const instanceId = runResult.Instances?.[0]?.InstanceId;

    // Update job with instance ID
    await supabaseRequest(
      'PATCH',
      `benchmark_jobs?id=eq.${jobId}`,
      { ec2_instance_id: instanceId, updated_at: new Date().toISOString() },
      supabaseKey,
    );

    return {
      statusCode: 200,
      headers: corsHeaders,
      body: JSON.stringify({ jobId, instanceId, status: 'launching' }),
    };
  } catch (err: any) {
    if (err instanceof AuthError) return { statusCode: err.status, headers: corsHeaders, body: JSON.stringify({ error: err.message }) };
    console.error('Error launching benchmark:', err);
    return {
      statusCode: 500,
      headers: corsHeaders,
      body: JSON.stringify({ error: err.message }),
    };
  }
};
