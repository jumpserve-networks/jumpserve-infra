/** IAM-only execution envelope; API Gateway callers cannot select this branch. */
import { AuthError } from './auth';
export type NetworkEnvelope = {source: 'jumpserve.network-execution'; job_id: string; action: 'launch' | 'status' | 'cancel'};
export function networkEnvelope(event: unknown): NetworkEnvelope | null {
  const value = event as Record<string, unknown>;
  if (!value || value.requestContext || value.source !== 'jumpserve.network-execution') return null;
  if (Object.keys(value).sort().join(',') !== 'action,job_id,source' || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(String(value.job_id)) || !['launch','status','cancel'].includes(String(value.action))) throw new AuthError(400, 'Invalid networking execution envelope.');
  return value as unknown as NetworkEnvelope;
}
export async function networkRpc(key: string, operation: string, body: object) {
  if (process.env.SUPABASE_URL !== 'https://regphejnlvfpyokpniny.supabase.co' || !['research_network_launch','research_network_update'].includes(operation)) throw new AuthError(503,'Networking target is misconfigured.');
  const response = await fetch(`${process.env.SUPABASE_URL}/rest/v1/rpc/${operation}`, {method:'POST',headers:{apikey:key,Authorization:`Bearer ${key}`,'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)});
  if (!response.ok) throw new AuthError(503,'Saved networking execution could not be verified.');
  return response.json();
}
