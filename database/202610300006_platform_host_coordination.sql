begin;
-- The existing 4-GB subscription host is preserved. Research has priority at
-- scheduling boundaries; neither worker may start native tools over the other.
do $install$
begin
 if to_regprocedure('public.research_model_dispatch(text,jsonb)') is not null then
  alter function public.research_model_dispatch(text,jsonb) rename to research_model_dispatch_before_platform_v1;
  revoke all on function public.research_model_dispatch_before_platform_v1(text,jsonb) from public,anon,authenticated,service_role;
  execute $definition$
   create function public.research_model_dispatch(p_operation text,p_payload jsonb) returns jsonb
   language plpgsql security definer set search_path='' as $body$
   begin
    if p_operation='claim' then
     perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
     if exists(select 1 from public.platform_tasks where lease_token is not null or checkpoint->>'cleanup_unknown'='true') then return null;end if;
    end if;
    return public.research_model_dispatch_before_platform_v1(p_operation,p_payload);
   end $body$
  $definition$;
  revoke all on function public.research_model_dispatch(text,jsonb) from public,anon,authenticated;
  grant execute on function public.research_model_dispatch(text,jsonb) to service_role;
 end if;
end $install$;
notify pgrst,'reload schema';
commit;
