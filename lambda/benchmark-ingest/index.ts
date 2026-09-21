import { createHash } from 'node:crypto';
import { gunzipSync } from 'node:zlib';
import { GetSecretValueCommand, SecretsManagerClient } from '@aws-sdk/client-secrets-manager';

const secrets = new SecretsManagerClient({});
const MAX_BODY = 4.1 * 1024 * 1024;

export async function handler(event: any) {
  const reply = (statusCode: number, body: unknown) => ({
    statusCode, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (event.requestContext?.http?.method !== 'POST') return reply(405, { error: 'POST required' });
  const authorization = event.headers?.authorization ?? event.headers?.Authorization ?? '';
  if (!/^Bearer [a-f0-9]{64}$/.test(authorization)) return reply(401, { error: 'Job token required' });
  let input: any;
  let payload: any;
  try {
    if (typeof event.body !== 'string' || event.body.length > MAX_BODY * 1.34) throw new Error();
    const body = event.isBase64Encoded ? Buffer.from(event.body, 'base64').toString('utf8') : event.body;
    if (Buffer.byteLength(body) > MAX_BODY) return reply(413, { error: 'Report too large' });
    input = JSON.parse(body);
    if (!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(input.job_id)) throw new Error();
    if (input.action === 'results') {
      if (typeof input.report_gzip !== 'string' || !/^[A-Za-z0-9+/]+={0,2}$/.test(input.report_gzip)) throw new Error();
      const compressed = Buffer.from(input.report_gzip, 'base64');
      if (compressed.length > 3 * 1024 * 1024) return reply(413, { error: 'Report too large' });
      payload = JSON.parse(gunzipSync(compressed, { maxOutputLength: 32 * 1024 * 1024 }).toString('utf8'));
    } else if (input.action === 'status' && ['installing', 'cloning', 'running', 'failed'].includes(input.status)) {
      payload = { status: input.status, error_message: typeof input.error_message === 'string' ? input.error_message.slice(0, 500) : null };
    } else throw new Error();
  } catch {
    return reply(400, { error: 'Invalid ingestion request' });
  }
  try {
    const { SecretString: key } = await secrets.send(new GetSecretValueCommand({ SecretId: process.env.SUPABASE_SECRET_ARN! }));
    if (!key) throw new Error();
    const response = await fetch(`${process.env.SUPABASE_URL}/rest/v1/rpc/benchmark_ingest`, {
      method: 'POST',
      headers: { apikey: key, 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: input.job_id, supplied_hash: createHash('sha256').update(authorization.slice(7)).digest('hex'), operation: input.action, payload }),
      signal: AbortSignal.timeout(50000),
    });
    if (!response.ok) {
      // Database errors may contain report data; neither log nor return them.
      const error = await response.json().catch(() => ({})) as { code?: string };
      if (error.code === '42501') return reply(403, { error: 'Invalid, expired, or closed job token' });
      if (response.status < 500) return reply(400, { error: 'Report rejected' });
      throw new Error();
    }
    return reply(200, await response.json());
  } catch {
    return reply(503, { error: 'Ingestion temporarily unavailable' });
  }
}
