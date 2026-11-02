begin;
-- Function creation inherits database-specific default EXECUTE grants. This
-- helper must only be reached through the existing leased worker RPC.
revoke all on function public.platform_repair_context_data(uuid) from public,anon,authenticated,service_role;
notify pgrst,'reload schema';
commit;
