import { gzipSync } from 'node:zlib';
import { createHash } from 'node:crypto';
import { SecretsManagerClient } from '@aws-sdk/client-secrets-manager';
import { handler } from '../lambda/benchmark-ingest';

const token = 'a'.repeat(64);
const job = '11111111-1111-4111-8111-111111111111';
const event = (body: object, authorization = `Bearer ${token}`) => ({
  requestContext: { http: { method: 'POST' } }, headers: { authorization }, body: JSON.stringify(body),
});
beforeEach(() => {
  process.env.SUPABASE_URL = 'https://example.supabase.co';
  jest.spyOn(SecretsManagerClient.prototype, 'send').mockResolvedValue({ SecretString: 'server-only-key' } as never);
});
afterEach(() => jest.restoreAllMocks());

test.each(['', 'Bearer browser-session', 'Bearer server-only-key'])('rejects non-job credentials before accessing secrets: %s', async (auth) => {
  const response = await handler(event({ job_id: job, action: 'status', status: 'running' }, auth));
  expect(response.statusCode).toBe(401);
  expect(SecretsManagerClient.prototype.send).not.toHaveBeenCalled();
});

test.each([
  { job_id: 'malformed', action: 'status', status: 'running' },
  { job_id: job, action: 'DELETE', table: 'runs' },
  { job_id: job, action: 'status', status: 'completed', parent_run_id: 123 },
  { job_id: job, action: 'results', report_gzip: 'invalid' },
  { job_id: job, action: 'results', report_gzip: gzipSync(Buffer.alloc(33 * 1024 * 1024)).toString('base64') },
])('rejects unsupported operations or invalid reports before DB access', async (body) => {
  expect((await handler(event(body))).statusCode).toBe(400);
  expect(SecretsManagerClient.prototype.send).not.toHaveBeenCalled();
});

test('hashes the job capability and invokes only the restricted RPC', async () => {
  const report = { parent: {}, runs: [], snapshots: [] };
  const fetch = jest.spyOn(globalThis, 'fetch').mockResolvedValue(Response.json({ parent_run_id: 42 }));
  const response = await handler(event({ job_id: job, action: 'results', report_gzip: gzipSync(JSON.stringify(report)).toString('base64') }));
  expect(response.statusCode).toBe(200);
  expect(fetch.mock.calls[0][0]).toBe('https://example.supabase.co/rest/v1/rpc/benchmark_ingest');
  const options = fetch.mock.calls[0][1]!;
  expect(options.headers).toEqual({ apikey: 'server-only-key', 'Content-Type': 'application/json' });
  expect(JSON.parse(options.body as string)).toEqual({ target: job, supplied_hash: createHash('sha256').update(token).digest('hex'), operation: 'results', payload: report });
  expect(response.body).not.toMatch(/server-only-key|supabase/);
});

test('does not return private database errors', async () => {
  jest.spyOn(globalThis, 'fetch').mockResolvedValue(Response.json({ code: '42501', message: 'private db contents' }, { status: 403 }));
  const response = await handler(event({ job_id: job, action: 'status', status: 'running' }));
  expect(response.statusCode).toBe(403);
  expect(response.body).not.toContain('private');
});
