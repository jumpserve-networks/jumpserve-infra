import {networkRpc} from '../lambda/shared/research-network';

const previous = process.env.SUPABASE_URL;
afterEach(() => {
  jest.restoreAllMocks();
  if (previous === undefined) delete process.env.SUPABASE_URL; else process.env.SUPABASE_URL = previous;
});
test.each(['research_network_launch', 'research_network_update'])('network RPC %s uses the fixed database, bounded request and service identity', async operation => {
  process.env.SUPABASE_URL = 'https://regphejnlvfpyokpniny.supabase.co';
  const fetch = jest.spyOn(globalThis, 'fetch').mockResolvedValue(Response.json({recorded: true}));
  await expect(networkRpc('synthetic-key', operation, {p_job: 'job'})).resolves.toEqual({recorded: true});
  expect(fetch.mock.calls[0][0]).toBe(`${process.env.SUPABASE_URL}/rest/v1/rpc/${operation}`);
  expect(fetch.mock.calls[0][1]).toMatchObject({method: 'POST', headers: {apikey: 'synthetic-key', Authorization: 'Bearer synthetic-key'}, body: '{"p_job":"job"}', signal: expect.any(AbortSignal)});
});
test('misconfigured targets and nonregistered operations fail before transport', async () => {
  const fetch = jest.spyOn(globalThis, 'fetch');
  process.env.SUPABASE_URL = 'https://other.test';
  await expect(networkRpc('key', 'research_network_launch', {})).rejects.toMatchObject({status: 503});
  process.env.SUPABASE_URL = 'https://regphejnlvfpyokpniny.supabase.co';
  await expect(networkRpc('key', 'arbitrary_operation', {})).rejects.toMatchObject({status: 503});
  expect(fetch).not.toHaveBeenCalled();
});
test('unconfirmed RPC persistence is not reported as successful', async () => {
  process.env.SUPABASE_URL = 'https://regphejnlvfpyokpniny.supabase.co';
  jest.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('private details', {status: 503}));
  await expect(networkRpc('key', 'research_network_update', {})).rejects.toMatchObject({status: 503, message: 'Saved networking execution could not be verified.'});
});
