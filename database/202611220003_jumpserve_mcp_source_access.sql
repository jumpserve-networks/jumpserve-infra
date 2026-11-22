begin;

alter table public.jumpserve_mcp_codes add column read_sources boolean not null default false;
alter table public.jumpserve_mcp_tokens add column read_sources boolean not null default false;

create function public.jumpserve_mcp_exchange_scoped(
  p_grant text, p_proof_hash text, p_client text, p_resource text,
  p_access text, p_refresh text, p_redirect text, p_challenge text, p_read_sources boolean
) returns text
language plpgsql security definer set search_path = '' as $$
declare granted boolean;
begin
  if p_grant = 'authorization_code' then
    select read_sources into granted from public.jumpserve_mcp_codes
      where code_hash = p_proof_hash and client_id = p_client and resource = p_resource;
  elsif p_grant = 'refresh_token' then
    select read_sources into granted from public.jumpserve_mcp_tokens
      where refresh_hash = p_proof_hash and client_id = p_client and resource = p_resource;
  end if;
  if granted is null or (p_read_sources is true and not granted) then return null; end if;
  if not public.jumpserve_mcp_exchange(p_grant, p_proof_hash, p_client, p_resource, p_access, p_refresh, p_redirect, p_challenge)
    then return null; end if;
  if granted and p_read_sources is distinct from false then
    update public.jumpserve_mcp_tokens set read_sources = true where access_hash = p_access;
    return 'source';
  end if;
  return 'share';
end
$$;

create function public.jumpserve_mcp_can_read_sources(p_access text, p_resource text)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.jumpserve_mcp_tokens t
    where t.access_hash = p_access and t.resource = p_resource and t.read_sources
      and t.owner_id = public.jumpserve_mcp_actor(p_access, p_resource)
  )
$$;

revoke all on function public.jumpserve_mcp_exchange_scoped(text,text,text,text,text,text,text,text,boolean),
  public.jumpserve_mcp_can_read_sources(text,text) from public, anon, authenticated;
grant execute on function public.jumpserve_mcp_exchange_scoped(text,text,text,text,text,text,text,text,boolean),
  public.jumpserve_mcp_can_read_sources(text,text) to service_role;

notify pgrst, 'reload schema';
commit;
