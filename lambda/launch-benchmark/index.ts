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
  if (!config.num_clients || config.num_clients < 1 || config.num_clients > 10) {
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
    if (d < 0 || d > 5000) return 'client_delays_ms values must be 0-5000';
  }
  for (const s of config.client_file_sizes_mbytes) {
    if (s < 0.1 || s > 1000) return 'client_file_sizes_mbytes values must be 0.1-1000';
  }
  if (config.bottleneck_all_client_rate_mbit < 1 || config.bottleneck_all_client_rate_mbit > 10000) {
    return 'bottleneck_all_client_rate_mbit must be 1-10000';
  }
  if (config.bottleneck_buffer_kbytes < 0 || config.bottleneck_buffer_kbytes > 100000) {
    return 'bottleneck_buffer_kbytes must be 0-100000';
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
    'Authorization': `Bearer ${key}`,
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
    const body = JSON.parse(event.body || '{}');
    const config: BenchmarkConfig = body.config;
    const requestedBy: string | undefined = body.requested_by;

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
      'benchmark_jobs?status=in.(launching,running)&select=id',
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

    // Build user data and launch EC2
    const userData = buildUserData(config, jobId, supabaseKey);

    const runResult = await ec2.send(new RunInstancesCommand({
      ImageId: process.env.AMI_ID!,
      InstanceType: 't3.medium',
      InstanceInitiatedShutdownBehavior: 'terminate',
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
    console.error('Error launching benchmark:', err);
    return {
      statusCode: 500,
      headers: corsHeaders,
      body: JSON.stringify({ error: err.message }),
    };
  }
};
