import { spawnSync } from 'node:child_process';
import { buildBenchmarkArgs, type BenchmarkConfig } from '../lambda/launch-benchmark/user-data';

// Supply a backend checkout to verify against the real argparse definitions.
// This imports the runners without starting namespaces, EC2, or Supabase writes.
const backend = process.env.JUMPSERVE_BACKEND_CHECKOUT;
const contractTest = backend ? test : test.skip;
const config: BenchmarkConfig = {
  num_clients: 2, client_delays_ms: [10, 20], client_ccas: ['cubic', 'cubic'],
  client_file_sizes_mbytes: [5, 5], client_start_delays_ms: [0, 0],
  bottleneck_all_client_rate_mbit: 100, bottleneck_buffer_kbytes: 125,
  bottleneck_rates_mbit: [100, 50], bottleneck_buffers_kbytes: [125, 64],
  client_groups: [1, 1], snapshot_metrics_source: 'ss', snapshot_interval_ms: 100,
  experiment_name: "topology's CLI test", tags: ['test'], notes: 'CLI contract', loss_pct: 0.1,
};

contractTest.each([
  ['netem_cubic_benchmark_hotnets.py', undefined],
  ['netem_cubic_benchmark_nines.py', undefined],
  ['netem_nines.py', undefined],
  ['netem_multi_bottleneck.py', 'parking-lot'],
  ['netem_multi_bottleneck.py', 'dumbbell'],
] as const)('%s %s accepts the generated launch arguments', (script, topology) => {
  const command = buildBenchmarkArgs({ ...config, script, topology });
  const result = spawnSync('python3', ['-B', '-c', `
import importlib, pathlib, shlex, sys
sys.path.insert(0, sys.argv[1])
tokens = shlex.split(sys.argv[2])
runner = importlib.import_module(pathlib.Path(tokens[3]).stem)
args = runner.build_parser().parse_args(tokens[4:])
assert args.num_clients == 2
`, backend!, command], { encoding: 'utf8' });
  expect({ status: result.status, error: result.stderr }).toEqual({ status: 0, error: '' });
});
