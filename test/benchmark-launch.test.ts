import { EC2Client, RunInstancesCommand } from '@aws-sdk/client-ec2';
import { SecretsManagerClient } from '@aws-sdk/client-secrets-manager';
import { handler } from '../lambda/launch-benchmark';

afterEach(() => jest.restoreAllMocks());

const multiConfig = {
  num_clients: 2, client_delays_ms: [10, 20], client_ccas: ['cubic', 'cubic'],
  client_file_sizes_mbytes: [5, 5], script: 'netem_multi_bottleneck.py',
  topology: 'dumbbell', bottleneck_rates_mbit: [100, 50],
  bottleneck_buffers_kbytes: [125, 64], client_groups: [1, 1],
};

test.each([
  { topology: undefined }, { topology: 'unknown' }, { topology: 'dumbbell; exit 1' },
  { bottleneck_rates_mbit: undefined }, { bottleneck_rates_mbit: [100] },
  { bottleneck_rates_mbit: [100, '50'] }, { bottleneck_rates_mbit: [100, null] },
  { bottleneck_rates_mbit: [0, 50] }, { bottleneck_buffers_kbytes: [125, -1] },
  { bottleneck_buffers_kbytes: [125, 64, 32] }, { bottleneck_buffers_kbytes: undefined },
  { client_groups: undefined }, { client_groups: [2, 1] }, { client_groups: [0, 2] },
  { client_groups: [1.5, 0.5] }, { client_groups: ['1', '1'] },
  { num_clients: 2.5 }, { client_start_delays_ms: [0, '0; exit 1'] },
  { snapshot_interval_ms: 0 }, { loss_pct: '1; exit 1' },
])('invalid multi-bottleneck config %j is rejected before any AWS or database access', async (invalid) => {
  const secrets = jest.spyOn(SecretsManagerClient.prototype, 'send');
  const ec2 = jest.spyOn(EC2Client.prototype, 'send');
  const fetch = jest.spyOn(globalThis, 'fetch');
  const response = await handler({ body: JSON.stringify({ config: { ...multiConfig, ...invalid } }) });
  expect(response.statusCode).toBe(400);
  expect(JSON.parse(response.body).error).toBeTruthy();
  expect(secrets).not.toHaveBeenCalled();
  expect(ec2).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});

test.each(['parking-lot', 'dumbbell'])('valid %s config reaches EC2 and is retained in the job', async (topology) => {
  jest.spyOn(SecretsManagerClient.prototype, 'send').mockResolvedValue({ SecretString: 'test-key' } as never);
  const ec2 = jest.spyOn(EC2Client.prototype, 'send').mockResolvedValue({ Instances: [{ InstanceId: 'i-test' }] } as never);
  let inserted: any;
  jest.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => {
    if (options?.method === 'GET') return Response.json([]);
    if (options?.method === 'POST') {
      inserted = JSON.parse(options.body as string);
      return Response.json([{ id: 'test-job' }]);
    }
    return new Response(null, { status: 204 });
  });
  const config = { ...multiConfig, topology, client_groups: topology === 'dumbbell' ? [1, 1] : undefined };
  const response = await handler({ body: JSON.stringify({ config }) });
  expect(response.statusCode).toBe(200);
  const command = ec2.mock.calls[0][0] as RunInstancesCommand;
  expect(command.input.InstanceInitiatedShutdownBehavior).toBe('terminate');
  const bootstrap = Buffer.from(command.input.UserData!, 'base64').toString();
  expect(bootstrap).toContain(`--topology ${topology}`);
  expect(bootstrap).toContain('--bottleneck-rates-mbit 100,50');
  expect(bootstrap).not.toContain('--bottleneck-all-client-rate-mbit');
  expect(inserted.config).toEqual(JSON.parse(JSON.stringify(config)));
});

test('launched benchmarks terminate on OS shutdown and retain metadata in the job', async () => {
  jest.spyOn(SecretsManagerClient.prototype, 'send').mockResolvedValue({ SecretString: 'test-key' } as never);
  const ec2 = jest.spyOn(EC2Client.prototype, 'send').mockResolvedValue({ Instances: [{ InstanceId: 'i-test' }] } as never);
  const requests: Array<{ method?: string; body?: unknown }> = [];
  jest.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => {
    requests.push({ method: options?.method, body: options?.body });
    if (options?.method === 'GET') return Response.json([]);
    if (options?.method === 'POST') return Response.json([{ id: 'test-job' }]);
    return new Response(null, { status: 204 });
  });

  const config = {
    num_clients: 2,
    client_delays_ms: [10, 20],
    client_ccas: ['cubic', 'cubic'],
    client_file_sizes_mbytes: [5, 5],
    bottleneck_all_client_rate_mbit: 10,
    bottleneck_buffer_kbytes: 125,
    script: 'netem_cubic_benchmark_nines.py',
    experiment_name: 'test',
  };
  const response = await handler({ body: JSON.stringify({ config }) });
  expect(response.statusCode).toBe(200);
  const command = ec2.mock.calls[0][0] as RunInstancesCommand;
  expect(command.input.InstanceInitiatedShutdownBehavior).toBe('terminate');
  const bootstrap = Buffer.from(command.input.UserData!, 'base64').toString();
  expect(bootstrap).toContain('trap finalize_benchmark EXIT');
  expect(bootstrap).not.toContain('--experiment-name');
  const inserted = requests.find((request) => request.method === 'POST');
  expect(JSON.parse(inserted!.body as string).config.experiment_name).toBe('test');
});
