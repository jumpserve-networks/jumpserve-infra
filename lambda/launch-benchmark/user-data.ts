export interface BenchmarkConfig {
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
  experiment_name?: string;
  tags?: string[];
  notes?: string;
}

export function buildBenchmarkArgs(config: BenchmarkConfig): string {
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
    if (config.snapshot_metrics_source === 'ss') {
      args.push('--ss-log-file /tmp/ss-log.jsonl');
    }
  }
  if (config.loss_pct !== undefined && config.loss_pct > 0) {
    args.push(`--loss-pct ${config.loss_pct}`);
  }
  if (config.snapshot_interval_ms !== undefined) {
    args.push(`--snapshot-interval-ms ${config.snapshot_interval_ms}`);
  }
  // Only the multi-bottleneck runner accepts these flags. All runners retain
  // the metadata in benchmark_jobs.config regardless of their CLI support.
  if (script === 'netem_multi_bottleneck.py') {
    if (config.experiment_name) {
      args.push(`--experiment-name '${config.experiment_name.replace(/'/g, "'\\''")}'`);
    }
    if (config.tags && config.tags.length > 0) {
      args.push(`--experiment-tags '${config.tags.join(',').replace(/'/g, "'\\''")}'`);
    }
    if (config.notes) {
      args.push(`--experiment-notes '${config.notes.replace(/'/g, "'\\''")}'`);
    }
  }
  return `sudo python3 /home/ubuntu/jumpserve-back-end/${script} ${args.join(' ')}`;
}

export function buildUserData(config: BenchmarkConfig, jobId: string, supabaseKey: string): string {
  const supabaseUrl = process.env.SUPABASE_URL!;
  const benchmarkCommand = buildBenchmarkArgs(config);

  const script = `#!/bin/bash
set -euo pipefail
BENCHMARK_PHASE=bootstrapping

# Helper: update job status in Supabase
update_status() {
  local STATUS="$1"
  local ERROR_MSG="\${2:-}"
  local PAYLOAD
  case "$STATUS" in
    installing|cloning|running) BENCHMARK_PHASE="$STATUS" ;;
  esac
  echo "Benchmark phase: $STATUS"
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
urllib.request.urlopen(req, timeout=10)
" || true
}

# Run on both success and failure, including failures before AWS CLI is installed.
# RunInstances sets InstanceInitiatedShutdownBehavior=terminate for this shutdown.
finalize_benchmark() {
  local exit_code=$?
  trap - EXIT
  set +e
  if [ "$exit_code" -ne 0 ]; then
    update_status "failed" "Benchmark failed during $BENCHMARK_PHASE (exit $exit_code)"
  fi
  echo "Benchmark bootstrap exited with code $exit_code; shutting down instance."
  if command -v systemctl >/dev/null && systemctl is-active --quiet amazon-cloudwatch-agent; then
    # Give the file collector time to read the final error, then flush on stop.
    sleep 5
    timeout 20 systemctl stop amazon-cloudwatch-agent || true
  fi
  shutdown -h now
  exit "$exit_code"
}
trap finalize_benchmark EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

# Phase: installing
update_status "installing"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq iproute2 ethtool python3 python3-pip git net-tools jq unzip < /dev/null

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
    "force_flush_interval": 1,
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
# Link parent_run_id and update final status after a successful benchmark.
# Find the most recently created parent run and link it to this job
PARENT_RUN_ID=$(python3 -c "
import urllib.request, json
req = urllib.request.Request(
  '${supabaseUrl}/rest/v1/emulated_parent_runs?order=created_at.desc&limit=1&select=id',
  headers={
      'apikey': '${supabaseKey}',
      'Authorization': 'Bearer ${supabaseKey}',
  }
)
resp = urllib.request.urlopen(req, timeout=10)
data = json.loads(resp.read())
print(data[0]['id'] if data else '')
" 2>/dev/null || echo "")

if [ -n "$PARENT_RUN_ID" ]; then
  python3 -c "
import urllib.request, json
req = urllib.request.Request(
  '${supabaseUrl}/rest/v1/benchmark_jobs?id=eq.${jobId}',
  data=json.dumps({'status': 'completed', 'parent_run_id': $PARENT_RUN_ID, 'updated_at': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'}).encode(),
  headers={
      'apikey': '${supabaseKey}',
      'Authorization': 'Bearer ${supabaseKey}',
      'Content-Type': 'application/json',
      'Prefer': 'return=minimal'
  },
  method='PATCH'
)
urllib.request.urlopen(req, timeout=10)
" || true
else
  update_status "completed"
fi

# The EXIT trap shuts down the instance without requiring AWS CLI or IMDS calls.
`;

  return Buffer.from(script).toString('base64');
}
