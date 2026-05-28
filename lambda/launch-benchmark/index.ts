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
const ALLOWED_SCRIPTS = ['netem_cubic_benchmark_hotnets.py', 'netem_cubic_benchmark_nines.py', 'netem_nines.py'];

interface BenchmarkConfig {
  num_clients: number;
  client_delays_ms: number[];
  client_ccas: string[];
  client_file_sizes_mbytes: number[];
  client_start_delays_ms?: number[];
  bottleneck_all_client_rate_mbit: number;
  bottleneck_buffer_kbytes: number;
  snapshot_metrics_source?: string;
  script?: string;
  loss_pct?: number;
  snapshot_interval_ms?: number;
}

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

function buildBenchmarkArgs(config: BenchmarkConfig): string {
  const script = config.script || 'netem_cubic_benchmark_hotnets.py';
  const args = [
    `--num-clients ${config.num_clients}`,
    `--client-delays-ms ${config.client_delays_ms.join(',')}`,
    `--client-ccas ${config.client_ccas.join(',')}`,
    `--client-file-sizes-mbytes ${config.client_file_sizes_mbytes.join(',')}`,
    `--bottleneck-all-client-rate-mbit ${config.bottleneck_all_client_rate_mbit}`,
    `--bottleneck-buffer-kbytes ${config.bottleneck_buffer_kbytes}`,
  ];
  if (config.client_start_delays_ms && config.client_start_delays_ms.length > 0) {
    args.push(`--client-start-delays-ms ${config.client_start_delays_ms.join(',')}`);
  }
  if (config.snapshot_metrics_source) {
    args.push(`--snapshot-metrics-source ${config.snapshot_metrics_source}`);
  }
  if (config.loss_pct !== undefined && config.loss_pct > 0) {
    args.push(`--loss-pct ${config.loss_pct}`);
  }
  if (config.snapshot_interval_ms !== undefined) {
    args.push(`--snapshot-interval-ms ${config.snapshot_interval_ms}`);
  }
  return `sudo python3 /home/ubuntu/jumpserve-back-end/${script} ${args.join(' ')}`;
}

function buildUserData(config: BenchmarkConfig, jobId: string, supabaseKey: string): string {
  const supabaseUrl = process.env.SUPABASE_URL!;
  const benchmarkCommand = buildBenchmarkArgs(config);

  const script = `#!/bin/bash
set -euxo pipefail

# Helper: update job status in Supabase
update_status() {
  local STATUS="$1"
  local ERROR_MSG="\${2:-}"
  local PAYLOAD
  if [ -n "$ERROR_MSG" ]; then
    PAYLOAD=$(python3 -c "import json; print(json.dumps({'status': '$STATUS', 'error_message': '$ERROR_MSG', 'updated_at': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'}))")
  else
    PAYLOAD=$(python3 -c "import json; print(json.dumps({'status': '$STATUS', 'updated_at': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'}))")
  fi
  python3 -c "
import urllib.request
req = urllib.request.Request(
    '${supabaseUrl}/rest/v1/benchmark_jobs?id=eq.${jobId}',
    data=b'$PAYLOAD',
    headers={
        'apikey': '${supabaseKey}',
        'Authorization': 'Bearer ${supabaseKey}',
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal'
    },
    method='PATCH'
)
urllib.request.urlopen(req)
" || true
}

# Phase: installing
update_status "installing"
apt-get update
apt-get install -y iproute2 ethtool python3 python3-pip git net-tools jq unzip

# Install AWS CLI
curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
./aws/install
rm -rf aws awscliv2.zip

# Install CloudWatch agent for log streaming
curl -s "https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb" -o "cwagent.deb"
dpkg -i cwagent.deb || true
rm -f cwagent.deb

# Configure CloudWatch agent to stream UserData output
mkdir -p /opt/aws/amazon-cloudwatch-agent/etc
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CWEOF'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/cloud-init-output.log",
            "log_group_name": "/jumpserve/benchmark",
            "log_stream_name": "${jobId}",
            "retention_in_days": 7
          }
        ]
      }
    }
  }
}
CWEOF
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json || true

# Phase: cloning
update_status "cloning"
cd /home/ubuntu
git clone https://github.com/jumpserve-networks/jumpserve-back-end.git
cd jumpserve-back-end

# Enable ip forwarding
sysctl -w net.ipv4.ip_forward=1

# Phase: running
update_status "running"

${benchmarkCommand} \\
  --supabase-project-id regphejnlvfpyokpniny \\
  --supabase-service-role-key '${supabaseKey}'
BENCHMARK_EXIT=$?

# Update final status
if [ $BENCHMARK_EXIT -eq 0 ]; then
  update_status "completed"
else
  update_status "failed" "Benchmark exited with code $BENCHMARK_EXIT"
fi

# Self-terminate
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --region ${process.env.AWS_REGION || 'us-east-1'}
`;

  return Buffer.from(script).toString('base64');
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
