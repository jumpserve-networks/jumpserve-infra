import {
  EC2Client,
  DescribeInstancesCommand,
  TerminateInstancesCommand,
} from '@aws-sdk/client-ec2';
import {
  SecretsManagerClient,
  GetSecretValueCommand,
} from '@aws-sdk/client-secrets-manager';

const ec2 = new EC2Client({});
const sm = new SecretsManagerClient({});

const MAX_RUNTIME_HOURS = 4;

async function supabaseRequest(method: string, path: string, body: object | undefined, apiKey: string): Promise<any> {
  const supabaseUrl = process.env.SUPABASE_URL!;
  const url = `${supabaseUrl}/rest/v1/${path}`;

  const headers: Record<string, string> = {
    'apikey': apiKey,
    'Authorization': `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal',
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

  if (method === 'GET') {
    return response.json();
  }
  return null;
}

export const handler = async () => {
  console.log('Running benchmark cleanup...');

  const secretResp = await sm.send(new GetSecretValueCommand({
    SecretId: process.env.SUPABASE_SECRET_ARN!,
  }));
  const supabaseKey = secretResp.SecretString!;

  // Find all running benchmark EC2 instances
  const describeResult = await ec2.send(new DescribeInstancesCommand({
    Filters: [
      { Name: 'tag:Project', Values: ['JumpServe'] },
      { Name: 'tag-key', Values: ['BenchmarkJobId'] },
      { Name: 'instance-state-name', Values: ['running', 'pending'] },
    ],
  }));

  const now = Date.now();
  const maxRuntimeMs = MAX_RUNTIME_HOURS * 60 * 60 * 1000;
  let terminatedCount = 0;

  for (const reservation of describeResult.Reservations || []) {
    for (const instance of reservation.Instances || []) {
      const launchTime = instance.LaunchTime?.getTime() || 0;
      const runtime = now - launchTime;

      if (runtime > maxRuntimeMs) {
        const instanceId = instance.InstanceId!;
        const jobIdTag = instance.Tags?.find(t => t.Key === 'BenchmarkJobId');
        const jobId = jobIdTag?.Value;

        console.log(`Terminating stale instance ${instanceId} (running ${Math.round(runtime / 3600000)}h, job: ${jobId})`);

        await ec2.send(new TerminateInstancesCommand({
          InstanceIds: [instanceId],
        }));

        if (jobId) {
          await supabaseRequest(
            'PATCH',
            `benchmark_jobs?id=eq.${jobId}`,
            {
              status: 'terminated',
              error_message: `Terminated after exceeding ${MAX_RUNTIME_HOURS} hour runtime limit`,
              updated_at: new Date().toISOString(),
            },
            supabaseKey,
          );
        }

        terminatedCount++;
      }
    }
  }

  // Also check for jobs stuck in 'launching' for more than 15 minutes
  const staleJobs = await supabaseRequest(
    'GET',
    `benchmark_jobs?status=eq.launching&updated_at=lt.${new Date(now - 15 * 60 * 1000).toISOString()}&select=id,ec2_instance_id`,
    undefined,
    supabaseKey,
  );

  for (const job of staleJobs || []) {
    console.log(`Marking stale launching job ${job.id} as failed`);

    if (job.ec2_instance_id) {
      try {
        await ec2.send(new TerminateInstancesCommand({
          InstanceIds: [job.ec2_instance_id],
        }));
      } catch (err) {
        console.warn(`Failed to terminate instance ${job.ec2_instance_id}:`, err);
      }
    }

    await supabaseRequest(
      'PATCH',
      `benchmark_jobs?id=eq.${job.id}`,
      {
        status: 'failed',
        error_message: 'Instance failed to start within 15 minutes',
        updated_at: new Date().toISOString(),
      },
      supabaseKey,
    );
  }

  console.log(`Cleanup complete. Terminated ${terminatedCount} stale instances, handled ${staleJobs?.length || 0} stale jobs.`);
};
