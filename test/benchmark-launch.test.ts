import { EC2Client, RunInstancesCommand } from '@aws-sdk/client-ec2';
import { SecretsManagerClient } from '@aws-sdk/client-secrets-manager';
import { handler } from '../lambda/launch-benchmark';

afterEach(() => jest.restoreAllMocks());

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
