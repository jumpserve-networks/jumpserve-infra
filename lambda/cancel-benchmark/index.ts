import {
  EC2Client,
  TerminateInstancesCommand,
} from '@aws-sdk/client-ec2';
import {
  SecretsManagerClient,
  GetSecretValueCommand,
} from '@aws-sdk/client-secrets-manager';

const ec2 = new EC2Client({});
const sm = new SecretsManagerClient({});

async function supabaseRequest(method: string, path: string, body: object | undefined, apiKey: string): Promise<any> {
  const supabaseUrl = process.env.SUPABASE_URL!;
  const url = `${supabaseUrl}/rest/v1/${path}`;

  const headers: Record<string, string> = {
    'apikey': apiKey,
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
    'Prefer': method === 'GET' ? 'return=representation' : 'return=minimal',
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

  if (method === 'GET') return response.json();
  return null;
}

export const handler = async (event: any) => {
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST,OPTIONS',
  };

  if (event.requestContext?.http?.method === 'OPTIONS') {
    return { statusCode: 200, headers: corsHeaders, body: '' };
  }

  try {
    const body = JSON.parse(event.body || '{}');
    const jobId: string = body.jobId;

    if (!jobId) {
      return {
        statusCode: 400,
        headers: corsHeaders,
        body: JSON.stringify({ error: 'jobId is required' }),
      };
    }

    const secretResp = await sm.send(new GetSecretValueCommand({
      SecretId: process.env.SUPABASE_SECRET_ARN!,
    }));
    const supabaseKey = secretResp.SecretString!;

    // Fetch the job to get the EC2 instance ID
    const jobs = await supabaseRequest(
      'GET',
      `benchmark_jobs?id=eq.${jobId}&select=id,status,ec2_instance_id`,
      undefined,
      supabaseKey,
    );

    if (!jobs || jobs.length === 0) {
      return {
        statusCode: 404,
        headers: corsHeaders,
        body: JSON.stringify({ error: 'Job not found' }),
      };
    }

    const job = jobs[0];
    const terminalStatuses = ['completed', 'failed', 'terminated', 'cancelled'];
    if (terminalStatuses.includes(job.status)) {
      return {
        statusCode: 400,
        headers: corsHeaders,
        body: JSON.stringify({ error: `Job is already ${job.status}` }),
      };
    }

    // Terminate the EC2 instance if it exists
    if (job.ec2_instance_id) {
      try {
        await ec2.send(new TerminateInstancesCommand({
          InstanceIds: [job.ec2_instance_id],
        }));
      } catch (err: any) {
        console.warn(`Failed to terminate instance ${job.ec2_instance_id}:`, err.message);
      }
    }

    // Update job status
    await supabaseRequest(
      'PATCH',
      `benchmark_jobs?id=eq.${jobId}`,
      { status: 'cancelled', updated_at: new Date().toISOString() },
      supabaseKey,
    );

    return {
      statusCode: 200,
      headers: corsHeaders,
      body: JSON.stringify({ jobId, status: 'cancelled' }),
    };
  } catch (err: any) {
    console.error('Error cancelling benchmark:', err);
    return {
      statusCode: 500,
      headers: corsHeaders,
      body: JSON.stringify({ error: err.message }),
    };
  }
};
