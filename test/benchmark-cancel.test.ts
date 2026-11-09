import {EC2Client, TerminateInstancesCommand} from '@aws-sdk/client-ec2';
import {SecretsManagerClient} from '@aws-sdk/client-secrets-manager';
import * as auth from '../lambda/shared/auth';
import {handler} from '../lambda/cancel-benchmark';

const jobId = 'abddfc29-4bd5-4372-90f9-927ee92378b9';
let send: jest.SpyInstance;
let fetchMock: jest.SpyInstance;
beforeEach(() => {
  jest.spyOn(auth, 'requireUser').mockResolvedValue({id: 'verified', email: undefined});
  jest.spyOn(console, 'error').mockImplementation(() => {});
  jest.spyOn(console, 'warn').mockImplementation(() => {});
  jest.spyOn(SecretsManagerClient.prototype, 'send').mockResolvedValue({SecretString: 'synthetic-key'} as never);
  send = jest.spyOn(EC2Client.prototype, 'send').mockResolvedValue({} as never);
  fetchMock = jest.spyOn(globalThis, 'fetch');
});
afterEach(() => jest.restoreAllMocks());
const request = (body: unknown = {jobId}) => ({body: JSON.stringify(body)});

test('preflight returns CORS before authentication or privileged access', async () => {
  const response = await handler({requestContext: {http: {method: 'OPTIONS'}}});
  expect(response).toMatchObject({statusCode: 200, body: '', headers: {'Access-Control-Allow-Methods': 'POST,OPTIONS'}});
  expect(auth.requireUser).not.toHaveBeenCalled();
  expect(fetchMock).not.toHaveBeenCalled();
});

test.each([{}, {jobId: 1}, {jobId: 'bad'}, {jobId: `${jobId}?other=1`}])('invalid job id never reaches the database: %j', async body => {
  expect(await handler(request(body))).toMatchObject({statusCode: 400});
  expect(fetchMock).not.toHaveBeenCalled();
});

test('missing body is handled as missing job id', async () => {
  expect(await handler({})).toMatchObject({statusCode: 400});
});

test.each([[], null])('missing jobs return 404 without termination or write', async jobs => {
  fetchMock.mockResolvedValueOnce(Response.json(jobs));
  expect(await handler(request())).toMatchObject({statusCode: 404});
  expect(send).not.toHaveBeenCalled();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test.each(['completed', 'failed', 'terminated', 'cancelled'])('terminal %s jobs cannot be cancelled again', async status => {
  fetchMock.mockResolvedValueOnce(Response.json([{status, ec2_instance_id: 'i-synthetic'}]));
  const response = await handler(request());
  expect(response.statusCode).toBe(400);
  expect(JSON.parse(response.body).error).toBe(`Job is already ${status}`);
  expect(send).not.toHaveBeenCalled();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test.each([false, true])('cancellation records state with an instance present=%s', async instance => {
  fetchMock.mockResolvedValueOnce(Response.json([{status: 'running', ec2_instance_id: instance ? 'i-synthetic' : null}]))
    .mockResolvedValueOnce(new Response(null, {status: 204}));
  const before = Date.now();
  const response = await handler(request());
  expect(JSON.parse(response.body)).toEqual({jobId, status: 'cancelled'});
  expect(response.statusCode).toBe(200);
  if (instance) {
    expect(send).toHaveBeenCalledTimes(1);
    expect(send.mock.calls[0][0]).toBeInstanceOf(TerminateInstancesCommand);
    expect(send.mock.calls[0][0].input).toEqual({InstanceIds: ['i-synthetic']});
  } else expect(send).not.toHaveBeenCalled();
  const [readURL, readOptions] = fetchMock.mock.calls[0];
  expect(readURL).toContain(`benchmark_jobs?id=eq.${jobId}&select=id,status,ec2_instance_id`);
  expect(readOptions).toMatchObject({method: 'GET', headers: {apikey: 'synthetic-key', Prefer: 'return=representation'}});
  expect(readOptions.body).toBeUndefined();
  const [writeURL, writeOptions] = fetchMock.mock.calls[1];
  expect(writeURL).toContain(`benchmark_jobs?id=eq.${jobId}`);
  expect(writeOptions).toMatchObject({method: 'PATCH', headers: {Prefer: 'return=minimal'}});
  const change = JSON.parse(writeOptions.body);
  expect(change.status).toBe('cancelled');
  expect(Date.parse(change.updated_at)).toBeGreaterThanOrEqual(before);
});

test('an instance termination error still records the cancellation', async () => {
  send.mockRejectedValueOnce(new Error('already terminated'));
  fetchMock.mockResolvedValueOnce(Response.json([{status: 'running', ec2_instance_id: 'i-synthetic'}]))
    .mockResolvedValueOnce(new Response(null, {status: 204}));
  expect(await handler(request())).toMatchObject({statusCode: 200});
  expect(console.warn).toHaveBeenCalledWith(expect.stringContaining('i-synthetic'), 'already terminated');
  expect(JSON.parse(fetchMock.mock.calls[1][1].body).status).toBe('cancelled');
});

test('database errors are reported and no unverified instance is terminated', async () => {
  fetchMock.mockResolvedValueOnce(new Response('database unavailable', {status: 503}));
  const response = await handler(request());
  expect(response.statusCode).toBe(500);
  expect(JSON.parse(response.body).error).toContain('503 database unavailable');
  expect(send).not.toHaveBeenCalled();
});

test('authentication failures keep their HTTP status', async () => {
  jest.mocked(auth.requireUser).mockRejectedValueOnce(new auth.AuthError(403, 'Google authentication is required.'));
  expect(await handler(request())).toMatchObject({statusCode: 403});
  expect(fetchMock).not.toHaveBeenCalled();
});

test('malformed JSON is reported without reading privileged state', async () => {
  expect(await handler({body: '{'})).toMatchObject({statusCode: 500});
  expect(fetchMock).not.toHaveBeenCalled();
});
