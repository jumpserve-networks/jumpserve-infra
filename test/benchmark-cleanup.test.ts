import {EC2Client, DescribeInstancesCommand, TerminateInstancesCommand} from '@aws-sdk/client-ec2';
import {SecretsManagerClient} from '@aws-sdk/client-secrets-manager';
import {handler} from '../lambda/cleanup-benchmarks';

const now = new Date('2026-11-06T12:00:00Z');
let send: jest.SpyInstance;
let fetchMock: jest.SpyInstance;
beforeEach(() => {
  jest.useFakeTimers({now});
  jest.spyOn(console, 'log').mockImplementation(() => {});
  jest.spyOn(console, 'warn').mockImplementation(() => {});
  jest.spyOn(SecretsManagerClient.prototype, 'send').mockResolvedValue({SecretString: 'synthetic-key'} as never);
  send = jest.spyOn(EC2Client.prototype, 'send');
  fetchMock = jest.spyOn(globalThis, 'fetch');
});
afterEach(() => {jest.useRealTimers(); jest.restoreAllMocks();});

test.each([{}, {Reservations: [{}]}, {Reservations: [{Instances: []}]}])('empty instance inventories still reconcile stale launch records: %j', async inventory => {
  send.mockResolvedValueOnce(inventory);
  fetchMock.mockResolvedValueOnce(Response.json(null));
  await handler();
  expect(send).toHaveBeenCalledTimes(1);
  expect(send.mock.calls[0][0]).toBeInstanceOf(DescribeInstancesCommand);
  expect(send.mock.calls[0][0].input.Filters).toContainEqual({Name: 'tag:Project', Values: ['JumpServe']});
  expect(fetchMock.mock.calls[0][0]).toContain('updated_at=lt.2026-11-06T11:45:00.000Z&select=id,ec2_instance_id');
  expect(fetchMock.mock.calls[0][1]).toMatchObject({method: 'GET', body: undefined});
});

test('only runtimes above four hours terminate, with durable state for tagged jobs', async () => {
  send.mockResolvedValueOnce({Reservations: [{Instances: [
    {InstanceId: 'i-boundary', LaunchTime: new Date(now.getTime() - 4 * 3600000)},
    {InstanceId: 'i-new', LaunchTime: new Date(now.getTime() - 1000)},
    {InstanceId: 'i-old', LaunchTime: new Date(now.getTime() - 4 * 3600000 - 1), Tags: [{Key: 'Name', Value: 'worker'}, {Key: 'BenchmarkJobId', Value: 'job-old'}]},
    {InstanceId: 'i-no-time'},
    {InstanceId: 'i-no-job', Tags: [{Key: 'Name', Value: 'worker'}]},
  ]}]}).mockResolvedValue({});
  fetchMock.mockResolvedValueOnce(new Response(null, {status: 204})).mockResolvedValueOnce(Response.json([]));
  await handler();
  const terminations = send.mock.calls.slice(1).map(([command]) => command.input.InstanceIds);
  expect(terminations).toEqual([['i-old'], ['i-no-time'], ['i-no-job']]);
  expect(send.mock.calls[1][0]).toBeInstanceOf(TerminateInstancesCommand);
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
    status: 'terminated', error_message: 'Terminated after exceeding 4 hour runtime limit', updated_at: now.toISOString(),
  });
  expect(fetchMock.mock.calls[0][1].headers).toMatchObject({apikey: 'synthetic-key', Authorization: 'Bearer synthetic-key', Prefer: 'return=minimal'});
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test('stale launches fail durably even if their instance is already gone', async () => {
  send.mockResolvedValueOnce({Reservations: []}).mockRejectedValueOnce(new Error('not found'));
  fetchMock.mockResolvedValueOnce(Response.json([{id: 'stale-instance', ec2_instance_id: 'i-gone'}, {id: 'stale-pending', ec2_instance_id: null}]))
    .mockResolvedValue(new Response(null, {status: 204}));
  await handler();
  expect(send).toHaveBeenCalledTimes(2);
  expect(console.warn).toHaveBeenCalledTimes(1);
  expect(fetchMock.mock.calls.slice(1).map(([url, options]) => [url.split('?')[1], JSON.parse(options.body)])).toEqual([
    ['id=eq.stale-instance', {status: 'failed', error_message: 'Instance failed to start within 15 minutes', updated_at: now.toISOString()}],
    ['id=eq.stale-pending', {status: 'failed', error_message: 'Instance failed to start within 15 minutes', updated_at: now.toISOString()}],
  ]);
});

test('successful stale instance termination precedes marking its job failed', async () => {
  send.mockResolvedValueOnce({}).mockResolvedValueOnce({});
  fetchMock.mockResolvedValueOnce(Response.json([{id: 'stale', ec2_instance_id: 'i-stale'}]))
    .mockResolvedValueOnce(new Response(null, {status: 204}));
  await handler();
  expect(send.mock.calls[1][0].input).toEqual({InstanceIds: ['i-stale']});
  expect(send.mock.invocationCallOrder[1]).toBeLessThan(fetchMock.mock.invocationCallOrder[1]);
});

test('failed persistence rejects cleanup instead of claiming a completed reconciliation', async () => {
  send.mockResolvedValueOnce({});
  fetchMock.mockResolvedValueOnce(new Response('unavailable', {status: 503}));
  await expect(handler()).rejects.toThrow('503 unavailable');
  expect(console.log).not.toHaveBeenCalledWith(expect.stringContaining('Cleanup complete'));
});
