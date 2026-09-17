import { spawnSync } from 'node:child_process';
import { buildBenchmarkArgs, buildUserData, type BenchmarkConfig } from '../lambda/launch-benchmark/user-data';

const config: BenchmarkConfig = {
  num_clients: 2,
  client_delays_ms: [10, 20],
  client_ccas: ['cubic', 'cubic'],
  client_file_sizes_mbytes: [5, 5],
  bottleneck_all_client_rate_mbit: 10,
  bottleneck_buffer_kbytes: 125,
  experiment_name: "test's experiment",
  tags: ['lifecycle', 'regression'],
  notes: "test's notes",
};

function userData(mode = 'base') {
  const previous = process.env.BENCHMARK_IMAGE_MODE;
  process.env.BENCHMARK_IMAGE_MODE = mode;
  try {
    return Buffer.from(buildUserData(config, 'test-job', 'test-service-key'), 'base64').toString();
  } finally {
    if (previous === undefined) delete process.env.BENCHMARK_IMAGE_MODE;
    else process.env.BENCHMARK_IMAGE_MODE = previous;
  }
}

test.each([
  'netem_cubic_benchmark_hotnets.py',
  'netem_cubic_benchmark_nines.py',
  'netem_nines.py',
])('%s does not receive unsupported metadata flags', (script) => {
  const command = buildBenchmarkArgs({ ...config, script });
  expect(command).not.toContain('--experiment-');
  expect(command).toContain(script);
  expect(config.experiment_name).toBe("test's experiment");
});

test('multi-bottleneck metadata is passed as intact shell arguments', () => {
  const command = buildBenchmarkArgs({ ...config, script: 'netem_multi_bottleneck.py',
    topology: 'parking-lot', bottleneck_rates_mbit: [100, 50], bottleneck_buffers_kbytes: [125, 125] });
  const result = spawnSync('bash', ['-c', `sudo() { printf '<%s>\\n' "$@"; }; ${command}`], { encoding: 'utf8' });
  expect(result.status).toBe(0);
  expect(result.stdout).toContain("<--experiment-name>\n<test's experiment>");
  expect(result.stdout).toContain('<--experiment-tags>\n<lifecycle,regression>');
  expect(result.stdout).toContain("<--experiment-notes>\n<test's notes>");
});

test.each(['parking-lot', 'dumbbell'] as const)('%s receives its own CLI flags without single-bottleneck flags', (topology) => {
  const command = buildBenchmarkArgs({
    ...config, script: 'netem_multi_bottleneck.py', topology,
    bottleneck_rates_mbit: [100, 50], bottleneck_buffers_kbytes: [125, 64],
    client_groups: [1, 1], snapshot_metrics_source: 'ss',
    client_start_delays_ms: [0, 250], snapshot_interval_ms: 50,
  });
  expect(command).toContain(`--topology ${topology}`);
  expect(command).toContain('--bottleneck-rates-mbit 100,50');
  expect(command).toContain('--bottleneck-buffers-kbytes 125,64');
  expect(command).toContain('--client-start-delays-ms 0,250');
  expect(command).toContain('--snapshot-interval-ms 50');
  expect(command.includes('--client-groups 1,1')).toBe(topology === 'dumbbell');
  expect(command).not.toMatch(/--bottleneck-all-client-rate-mbit|--bottleneck-buffer-kbytes|--snapshot-metrics-source|--ss-log-file/);
});

test.each(['netem_cubic_benchmark_hotnets.py', 'netem_cubic_benchmark_nines.py', 'netem_nines.py'])(
  '%s retains single-bottleneck settings and ignores leftover topology settings', (script) => {
    const command = buildBenchmarkArgs({ ...config, script, snapshot_metrics_source: 'ss', topology: 'dumbbell',
      bottleneck_rates_mbit: [100, 50], bottleneck_buffers_kbytes: [125, 64], client_groups: [1, 1] });
    expect(command).toContain('--bottleneck-all-client-rate-mbit 10');
    expect(command).toContain('--bottleneck-buffer-kbytes 125');
    expect(command).toContain('--snapshot-metrics-source ss --ss-log-file /tmp/ss-log.jsonl');
    expect(command).not.toMatch(/--topology|--client-groups|--bottleneck-rates-mbit|--bottleneck-buffers-kbytes/);
  },
);

test('generated bootstrap is valid bash and does not enable credential tracing', () => {
  const script = userData();
  expect(spawnSync('bash', ['-n'], { input: script }).status).toBe(0);
  expect(script).not.toMatch(/set -[^\n]*x/);
  expect(script).toContain('urlopen(req, timeout=10)');
});

test('prebuilt instances run the baked backend without installing or fetching software', () => {
  const script = userData('prebaked');
  expect(spawnSync('bash', ['-n'], { input: script }).status).toBe(0);
  expect(script).not.toMatch(/apt-get|dpkg|pip install|git (clone|pull|fetch)|curl /);
  expect(script).toContain('/etc/jumpserve-image.json');
  expect(script).toContain("manifest.get('schema_version') == 1");
  expect(script).toContain('Benchmark image backend commit:');
  expect(script).toContain('"log_stream_name": "test-job"');
  expect(script).toContain('trap finalize_benchmark EXIT');
  expect(script).not.toMatch(/set -[^\n]*x/);
});

test('base-image rollback retains dependency installation and a fresh backend checkout', () => {
  const script = userData('base');
  expect(script).toContain('apt-get install');
  expect(script).toContain('git clone https://github.com/jumpserve-networks/jumpserve-back-end.git');
});

function runFinalizer(body: string, failStatusUpdate = false, activeLogAgent = false) {
  const setup = userData().split('# Phase: installing')[0];
  // Exercise the actual generated traps without running setup, network calls,
  // or a real shutdown. The shell functions replace those two side effects.
  return spawnSync('bash', ['-c', `${setup}
update_status() {
  printf 'STATUS:%s:%s\\n' "$1" "\${2:-}"
  return ${failStatusUpdate ? 1 : 0}
}
shutdown() { echo SHUTDOWN; }
systemctl() { return ${activeLogAgent ? 0 : 1}; }
sleep() { echo LOG_COLLECTION_WAIT; }
timeout() { echo LOG_FLUSH; return 1; }
${body}
`], { encoding: 'utf8' });
}

test('successful completion always shuts down once', () => {
  const result = runFinalizer('exit 0');
  expect(result.status).toBe(0);
  expect(result.stdout.match(/SHUTDOWN/g)).toHaveLength(1);
  expect(result.stdout).not.toContain('STATUS:failed');
});

test.each([
  ['installing', 17],
  ['cloning', 128],
  ['running', 2],
])('a failed %s command reports failure and shuts down', (phase, exitCode) => {
  const result = runFinalizer(`BENCHMARK_PHASE=${phase}\nbash -c 'exit ${exitCode}'`);
  expect(result.status).toBe(exitCode);
  expect(result.stdout).toContain(`STATUS:failed:Benchmark failed during ${phase} (exit ${exitCode})`);
  expect(result.stdout.match(/SHUTDOWN/g)).toHaveLength(1);
  expect(result.stdout + result.stderr).not.toContain('test-service-key');
});

test('a failed status update cannot prevent shutdown', () => {
  const result = runFinalizer('exit 2', true);
  expect(result.status).toBe(2);
  expect(result.stdout).toContain('SHUTDOWN');
});

test('termination signals go through failure reporting and shutdown', () => {
  const result = runFinalizer('kill -TERM $$');
  expect(result.status).toBe(143);
  expect(result.stdout).toContain('STATUS:failed:');
  expect(result.stdout.match(/SHUTDOWN/g)).toHaveLength(1);
});

test('log flushing happens before shutdown and cannot block it on failure', () => {
  const result = runFinalizer('exit 2', false, true);
  expect(result.status).toBe(2);
  expect(result.stdout.indexOf('LOG_COLLECTION_WAIT')).toBeLessThan(result.stdout.indexOf('LOG_FLUSH'));
  expect(result.stdout.indexOf('LOG_FLUSH')).toBeLessThan(result.stdout.indexOf('SHUTDOWN'));
});
