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
  topology?: 'parking-lot' | 'dumbbell';
  bottleneck_rates_mbit?: number[];
  bottleneck_buffers_kbytes?: number[];
  client_groups?: number[];
  loss_pct?: number;
  snapshot_interval_ms?: number;
  experiment_name?: string;
  tags?: string[];
  notes?: string;
}

export function buildBenchmarkArgs(config: BenchmarkConfig): string {
  const script = config.script || 'netem_cubic_benchmark_hotnets.py';
  const multiBottleneck = script === 'netem_multi_bottleneck.py';
  const args = [
    `--num-clients ${config.num_clients}`,
    `--client-delays-ms ${config.client_delays_ms.join(',')}`,
    `--client-ccas ${config.client_ccas.join(',')}`,
    `--client-file-sizes-mbytes ${config.client_file_sizes_mbytes.join(',')}`,
  ];
  if (multiBottleneck) {
    // Required by this runner; validation rejects missing topology/link settings
    // before creating a job or starting an instance.
    args.push(
      `--topology ${config.topology}`,
      `--bottleneck-rates-mbit ${config.bottleneck_rates_mbit!.join(',')}`,
      `--bottleneck-buffers-kbytes ${config.bottleneck_buffers_kbytes!.join(',')}`,
    );
    if (config.topology === 'dumbbell') {
      args.push(`--client-groups ${config.client_groups!.join(',')}`);
    }
  } else {
    args.push(
      `--bottleneck-all-client-rate-mbit ${config.bottleneck_all_client_rate_mbit}`,
      `--bottleneck-buffer-kbytes ${config.bottleneck_buffer_kbytes}`,
    );
  }
  if (config.client_start_delays_ms && config.client_start_delays_ms.length > 0) {
    args.push(`--client-start-delays-ms ${config.client_start_delays_ms.join(',')}`);
  }
  if (!multiBottleneck && config.snapshot_metrics_source) {
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
  return `sudo --preserve-env=JUMPSERVE_INGEST_URL,JUMPSERVE_JOB_ID,JUMPSERVE_JOB_TOKEN python3 /home/ubuntu/jumpserve-back-end/${script} ${args.join(' ')}`;
}

export function buildUserData(config: BenchmarkConfig, jobId: string, jobToken: string): string {
  const ingestUrl = process.env.BENCHMARK_INGEST_URL!;
  if (!/^https:\/\/[a-z0-9.-]+\/benchmarks\/ingest$/.test(ingestUrl) ||
      !/^[a-f0-9-]{36}$/i.test(jobId) || !/^[a-f0-9]{64}$/.test(jobToken)) {
    throw new Error('Invalid job ingestion configuration');
  }
  const benchmarkCommand = buildBenchmarkArgs(config);
  const prebaked = process.env.BENCHMARK_IMAGE_MODE === 'prebaked';
  const installation = prebaked ? `
echo "Preparing prebuilt benchmark image"
test -x /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl
` : `
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq iproute2 ethtool python3 python3-pip git net-tools jq unzip < /dev/null

curl -s "https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb" -o "cwagent.deb"
dpkg -i cwagent.deb
rm -f cwagent.deb
`;
  const backendPreparation = prebaked ? `
# Reject an incorrect or incomplete image instead of silently installing at boot.
python3 - <<'IMAGECHECK'
import json, pathlib, re, shutil
manifest = json.loads(pathlib.Path('/etc/jumpserve-image.json').read_text())
assert manifest.get('schema_version') == 1, 'Unsupported benchmark image schema'
assert re.fullmatch('[0-9a-f]{40}', manifest.get('backend_commit', '')), 'Missing backend commit'
for command in ('ip', 'tc', 'ss', 'ethtool', 'python3', 'sysctl', 'shutdown', 'timeout'):
    assert shutil.which(command), f'Missing image dependency: {command}'
for runner in ('benchmark_ingest.py', 'netem_cubic_benchmark_hotnets.py', 'netem_cubic_benchmark_nines.py', 'netem_nines.py', 'netem_multi_bottleneck.py'):
    assert pathlib.Path('/home/ubuntu/jumpserve-back-end', runner).is_file(), f'Missing runner: {runner}'
print('Benchmark image backend commit: ' + manifest['backend_commit'], flush=True)
IMAGECHECK
cd /home/ubuntu/jumpserve-back-end
` : `
update_status "cloning"
cd /home/ubuntu
git clone --depth 1 https://github.com/jumpserve-networks/jumpserve-back-end.git
cd jumpserve-back-end
`;

  const script = `#!/bin/bash
set -euo pipefail
BENCHMARK_PHASE=bootstrapping

# This capability is scoped to this job and expires after 45 minutes.
export JUMPSERVE_INGEST_URL='${ingestUrl}'
export JUMPSERVE_JOB_ID='${jobId}'
export JUMPSERVE_JOB_TOKEN='${jobToken}'

update_status() {
  local STATUS="$1"
  local ERROR_MSG="\${2:-}"
  case "$STATUS" in
    installing|cloning|running) BENCHMARK_PHASE="$STATUS" ;;
  esac
  echo "Benchmark phase: $STATUS"
  python3 - "$STATUS" "$ERROR_MSG" <<'STATUSUPDATE' || true
import json, os, sys, urllib.request
request = urllib.request.Request(os.environ['JUMPSERVE_INGEST_URL'], method='POST',
    data=json.dumps({'job_id': os.environ['JUMPSERVE_JOB_ID'], 'action': 'status',
        'status': sys.argv[1], 'error_message': sys.argv[2]}).encode(),
    headers={'Authorization': 'Bearer ' + os.environ['JUMPSERVE_JOB_TOKEN'],
        'Content-Type': 'application/json'})
try:
    urllib.request.urlopen(request, timeout=10).close()
except Exception:
    print('Job status update unavailable', file=sys.stderr)
STATUSUPDATE
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
${installation}

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
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

# Phase: preparing backend
${backendPreparation}

# Enable ip forwarding
sysctl -w net.ipv4.ip_forward=1

# Phase: running
update_status "running"

# The runner commits the complete report and marks this exact job completed.
${benchmarkCommand}

# The EXIT trap shuts down the instance without requiring AWS CLI or IMDS calls.
`;

  return Buffer.from(script).toString('base64');
}
