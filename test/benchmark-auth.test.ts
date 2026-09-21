import { EC2Client } from '@aws-sdk/client-ec2';
import { SecretsManagerClient } from '@aws-sdk/client-secrets-manager';
import { handler as launch } from '../lambda/launch-benchmark';
import { handler as cancel } from '../lambda/cancel-benchmark';
import { requireUser } from '../lambda/shared/auth';

afterEach(() => jest.restoreAllMocks());

test.each([launch, cancel])('anonymous mutations are denied before AWS, database, or auth network access', async (handler) => {
  const ec2 = jest.spyOn(EC2Client.prototype, 'send');
  const secrets = jest.spyOn(SecretsManagerClient.prototype, 'send');
  const fetch = jest.spyOn(globalThis, 'fetch');
  const response = await handler({ body: '{}' });
  expect(response.statusCode).toBe(401);
  expect(ec2).not.toHaveBeenCalled();
  expect(secrets).not.toHaveBeenCalled();
  expect(fetch).not.toHaveBeenCalled();
});

test.each([launch, cancel])('forged tokens are denied before privileged access', async (handler) => {
  const ec2 = jest.spyOn(EC2Client.prototype, 'send');
  const secrets = jest.spyOn(SecretsManagerClient.prototype, 'send');
  jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 401 }));
  const response = await handler({ headers: { Authorization: 'Bearer forged' }, body: '{}' });
  expect(response.statusCode).toBe(401);
  expect(ec2).not.toHaveBeenCalled();
  expect(secrets).not.toHaveBeenCalled();
});

test.each([
  [{ id: 'user', is_anonymous: true, identities: [{ provider: 'google' }] }, 403],
  [{ id: 'user', identities: [{ provider: 'email' }] }, 403],
  [{}, 403],
])('unverified providers and anonymous Auth users cannot execute tests', async (user, status) => {
  jest.spyOn(globalThis, 'fetch').mockResolvedValue(Response.json(user));
  await expect(requireUser({ headers: { authorization: 'Bearer session' } })).rejects.toMatchObject({ status });
});

test('verified caller identity comes from Auth, with a bounded request timeout', async () => {
  const fetch = jest.spyOn(globalThis, 'fetch').mockResolvedValue(Response.json({ id: 'verified', email: 'verified@example.test', identities: [{ provider: 'google' }] }));
  await expect(requireUser({ headers: { AUTHORIZATION: 'Bearer session' } })).resolves.toEqual({ id: 'verified', email: 'verified@example.test' });
  expect(fetch.mock.calls[0][1]?.headers).toMatchObject({ Authorization: 'Bearer session' });
  expect(fetch.mock.calls[0][1]?.signal).toBeInstanceOf(AbortSignal);
});

test('auth outages fail closed', async () => {
  jest.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network'));
  await expect(requireUser({ headers: { authorization: 'Bearer session' } })).rejects.toMatchObject({ status: 503 });
});

test('an HTTP request cannot impersonate the IAM-only verification envelope', async () => {
  const ec2 = jest.spyOn(EC2Client.prototype, 'send');
  const response = await launch({
    source: 'jumpserve.ami-verification', body: '{}',
    requestContext: { http: { method: 'POST' } },
  });
  expect(response.statusCode).toBe(401);
  expect(ec2).not.toHaveBeenCalled();
  ec2.mockRestore();
});
