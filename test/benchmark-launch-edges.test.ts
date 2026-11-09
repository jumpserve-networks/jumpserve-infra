process.env.BENCHMARK_INGEST_URL = 'https://example.test/benchmarks/ingest';
import {EC2Client} from '@aws-sdk/client-ec2';
import {SecretsManagerClient} from '@aws-sdk/client-secrets-manager';
import * as auth from '../lambda/shared/auth';
import * as network from '../lambda/shared/research-network';
import {handler} from '../lambda/launch-benchmark';

const id = 'acbac032-92f6-4659-98ba-2ab47b83523c';
const config = {num_clients: 1, client_delays_ms: [0], client_ccas: ['cubic'], client_file_sizes_mbytes: [1], bottleneck_all_client_rate_mbit: 10, bottleneck_buffer_kbytes: 0};
let fetchMock: jest.SpyInstance;
let send: jest.SpyInstance;
beforeEach(() => {
  jest.spyOn(auth, 'requireUser').mockResolvedValue({id: 'verified-user', email: undefined});
  jest.spyOn(console, 'error').mockImplementation(() => {});
  jest.spyOn(SecretsManagerClient.prototype, 'send').mockResolvedValue({SecretString: 'synthetic-key'} as never);
  send = jest.spyOn(EC2Client.prototype, 'send').mockResolvedValue({Instances: [{InstanceId: 'i-synthetic'}]} as never);
  fetchMock = jest.spyOn(globalThis, 'fetch');
});
afterEach(() => jest.restoreAllMocks());

test.each([
  {client_delays_ms: null}, {client_delays_ms: []}, {client_delays_ms: [-1]},
  {client_ccas: null}, {client_ccas: []}, {client_ccas: ['unsupported']},
  {client_file_sizes_mbytes: null}, {client_file_sizes_mbytes: []}, {client_file_sizes_mbytes: [0]},
  {bottleneck_all_client_rate_mbit: 0}, {bottleneck_buffer_kbytes: -1},
  {snapshot_metrics_source: 'unsupported'}, {script: 'arbitrary.py'},
])('invalid scalar/single-bottleneck configuration is rejected before AWS: %j', async change => {
  expect(await handler({body: JSON.stringify({config: {...config, ...change}})})).toMatchObject({statusCode: 400});
  expect(SecretsManagerClient.prototype.send).not.toHaveBeenCalled();
  expect(send).not.toHaveBeenCalled(); expect(fetchMock).not.toHaveBeenCalled();
});

test('preflight, missing configuration and malformed JSON never launch a machine', async () => {
  expect(await handler({requestContext: {http: {method: 'OPTIONS'}}})).toMatchObject({statusCode: 200, body: ''});
  expect(auth.requireUser).not.toHaveBeenCalled();
  expect(await handler({})).toMatchObject({statusCode: 400});
  expect(await handler({body: '{'})).toMatchObject({statusCode: 500});
  expect(send).not.toHaveBeenCalled();
});

test('five existing active jobs deny a new launch without inserting a job', async () => {
  fetchMock.mockResolvedValueOnce(Response.json(Array.from({length: 5}, (_, id) => ({id}))));
  expect(await handler({body: JSON.stringify({config})})).toMatchObject({statusCode: 429});
  expect(fetchMock).toHaveBeenCalledTimes(1); expect(send).not.toHaveBeenCalled();
});

test('database outages do not proceed to instance launch', async () => {
  fetchMock.mockResolvedValueOnce(new Response('database unavailable', {status: 503}));
  const response = await handler({body: JSON.stringify({config})});
  expect(response.statusCode).toBe(500);
  expect(JSON.parse(response.body).error).toContain('503 database unavailable');
  expect(send).not.toHaveBeenCalled();
});

test('an incomplete EC2 acknowledgement does not invent an instance id or requester email', async () => {
  send.mockResolvedValueOnce({});
  fetchMock.mockImplementation(async (_url, options) => options?.method === 'GET' ? Response.json([]) : options?.method === 'POST' ? Response.json([{id}]) : new Response(null, {status: 204}));
  const response = await handler({body: JSON.stringify({config, requested_by: 'forged'})});
  expect(JSON.parse(response.body)).toEqual({jobId: id, status: 'launching'});
  expect(JSON.parse(fetchMock.mock.calls[1][1].body).requested_by).toBe('verified-user');
  expect(JSON.parse(fetchMock.mock.calls.at(-1)![1].body)).not.toHaveProperty('ec2_instance_id');
});

test('the configured service-key fallback is server-side and absent from the launch response', async () => {
  const previous = process.env.SUPABASE_SERVICE_KEY;
  process.env.SUPABASE_SERVICE_KEY = 'synthetic-environment-key';
  jest.mocked(SecretsManagerClient.prototype.send).mockResolvedValueOnce({SecretString: ''} as never);
  fetchMock.mockImplementation(async (_url, options) => options?.method === 'GET' ? Response.json([]) : options?.method === 'POST' ? Response.json([{id}]) : new Response(null, {status: 204}));
  try {
    const response = await handler({body: JSON.stringify({config})});
    expect(response.statusCode).toBe(200);
    expect(fetchMock.mock.calls[0][1].headers.apikey).toBe('synthetic-environment-key');
    expect(response.body).not.toContain('synthetic-environment-key');
  } finally {if (previous === undefined) delete process.env.SUPABASE_SERVICE_KEY; else process.env.SUPABASE_SERVICE_KEY = previous;}
});

const envelope = (action: 'launch' | 'status' | 'cancel') => ({source: 'jumpserve.network-execution', job_id: id, action});
const saved = (change = {}) => ({owner_id: 'owner', started_at: '2026-11-01T00:00:00Z', deadline: '2100-01-01T00:00:00Z', spec: {config}, ...change});

test('an absent immutable invocation returns 404 without inspecting or launching machines', async () => {
  const rpc = jest.spyOn(network, 'networkRpc').mockResolvedValue(null);
  expect(await handler(envelope('launch'))).toMatchObject({statusCode: 404});
  expect(rpc).toHaveBeenCalledTimes(2); expect(send).not.toHaveBeenCalled(); expect(fetchMock).not.toHaveBeenCalled();
});

test.each([{}, {Reservations: [{}]}])('status with no recorded job or machine remains unconfirmed: %j', async machines => {
  jest.spyOn(network, 'networkRpc').mockResolvedValue(saved());
  fetchMock.mockResolvedValueOnce(Response.json([])); send.mockResolvedValueOnce(machines);
  const response = await handler(envelope('status'));
  const value = JSON.parse(response.body);
  expect(value).toMatchObject({status: 'launch-unconfirmed', started_at: '2026-11-01T00:00:00Z', ended_at: null, resources: {instance_id: null, instance_type: null, image_id: null}});
  expect(send).toHaveBeenCalledTimes(1);
  expect(send.mock.calls[0][0].constructor.name).toBe('DescribeInstancesCommand');
  expect(auth.requireUser).not.toHaveBeenCalled();
});

test('multiple machine matches are an error, never another launch', async () => {
  jest.spyOn(network, 'networkRpc').mockResolvedValue(saved());
  fetchMock.mockResolvedValueOnce(Response.json([]));
  send.mockResolvedValueOnce({Reservations: [{Instances: [{InstanceId: 'i-a'}, {InstanceId: 'i-b'}]}]});
  const response = await handler(envelope('status'));
  expect(response.statusCode).toBe(500);
  expect(JSON.parse(response.body).error).toContain('Multiple machines');
  expect(send).toHaveBeenCalledTimes(1);
});

test('cancel uses the recorded machine identity and waits for confirmed termination', async () => {
  jest.spyOn(network, 'networkRpc').mockResolvedValue(saved());
  fetchMock.mockResolvedValueOnce(Response.json([{id, status: 'running', ec2_instance_id: 'i-known', created_at: '2026-11-01T01:00:00Z'}]))
    .mockResolvedValueOnce(new Response(null, {status: 204}));
  send.mockResolvedValueOnce({Reservations: [{Instances: [{InstanceId: 'i-known'}]}]}).mockResolvedValueOnce({});
  const response = await handler(envelope('cancel'));
  expect(JSON.parse(response.body)).toMatchObject({status: 'cleaning', ended_at: null, started_at: '2026-11-01T01:00:00Z'});
  expect(send.mock.calls[0][0].input).toEqual({InstanceIds: ['i-known']});
  expect(send.mock.calls[1][0].input).toEqual({InstanceIds: ['i-known']});
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toMatchObject({status: 'cancelled'});
});

test('expired unrecorded launches return failed without inventing measurements', async () => {
  jest.spyOn(network, 'networkRpc').mockResolvedValue(saved({deadline: '2000-01-01T00:00:00Z'}));
  fetchMock.mockResolvedValueOnce(Response.json([])); send.mockResolvedValueOnce({});
  const value = JSON.parse((await handler(envelope('status'))).body);
  expect(value.status).toBe('failed'); expect(value.ended_at).toEqual(expect.any(String));
  expect(value.reason).toContain('not confirmed before its deadline'); expect(value).not.toHaveProperty('output');
});

test('completed recordings expose zero and missing values separately after resource cleanup', async () => {
  jest.spyOn(network, 'networkRpc').mockResolvedValue(saved());
  fetchMock.mockResolvedValueOnce(Response.json([{id, status: 'completed', ec2_instance_id: 'i-done', parent_run_id: 42, updated_at: '2026-11-01T02:00:00Z'}]))
    .mockResolvedValueOnce(Response.json([{id: 1, client_number: 1, flow_completion_time_ms: '0'}, {id: 2, client_number: 2, flow_completion_time_ms: null}]));
  send.mockResolvedValueOnce({Reservations: [{Instances: [{InstanceId: 'i-done', State: {Name: 'terminated'}, InstanceType: 't3.medium', ImageId: 'ami-synthetic'}]}]});
  const value = JSON.parse((await handler(envelope('status'))).body);
  expect(value).toMatchObject({status: 'completed', ended_at: '2026-11-01T02:00:00Z', resources: {instance_type: 't3.medium', image_id: 'ami-synthetic'}});
  expect(value.output.observations).toEqual([
    expect.objectContaining({value: 0, status: 'recorded', reason: null, metadata: {emulated_run_id: 1, parent_run_id: 42}}),
    expect.objectContaining({value: null, status: 'missing', reason: 'Completion time unavailable.'}),
  ]);
  expect(send).toHaveBeenCalledTimes(1);
});

test('cancelled jobs retain their error and instance identity even when EC2 no longer returns them', async () => {
  jest.spyOn(network, 'networkRpc').mockResolvedValue(saved());
  fetchMock.mockResolvedValueOnce(Response.json([{id, status: 'cancelled', ec2_instance_id: 'i-retained', error_message: 'Owner cancelled'}]));
  send.mockResolvedValueOnce({Reservations: []});
  const value = JSON.parse((await handler(envelope('status'))).body);
  expect(value).toMatchObject({status: 'cancelled', reason: 'Owner cancelled', resources: {instance_id: 'i-retained'}});
  expect(value.ended_at).toEqual(expect.any(String));
});
