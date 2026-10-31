begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));

-- The deployed v2 resource policy retained the same unlimited-turn semantics,
-- but the startup RPC still rejected its version before any ordinary lease.
-- Change only that compatibility literal; retain every resumption fence.
do $$declare definition text;needle text;begin
 definition=pg_get_functiondef('public.research_autonomy_resume_turns(text)'::regprocedure);
 needle='p_policy is distinct from ''autonomy-turn-policy-v1''';
 if strpos(definition,needle)=0 then raise exception 'Unexpected controller turn-policy guard';end if;
 execute replace(definition,needle,'p_policy is distinct from ''autonomy-turn-policy-v2''');
end$$;

create function public.research_autonomy_runtime_observe(p_action text,p_details jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare identity uuid;begin
 if p_action is distinct from 'maintenance-failed' or p_details->>'version' is distinct from 'research-controller-health-v1'
  or not coalesce(p_details->>'component' in ('repair-discovery','turn-recovery','context-recovery'),false)
  or not coalesce(p_details->>'error_type' in ('StoreError','ValueError','KeyError','TypeError','IndexError'),false)
  or p_details->>'policy' is distinct from 'autonomy-turn-policy-v2'
  or jsonb_typeof(p_details) is distinct from 'object' or octet_length(p_details::text)>2048
  or (select count(*) from jsonb_object_keys(p_details))<>4
 then raise exception 'Bounded controller health observation required';end if;
 identity=md5('research-controller-health-v1:'||p_details::text||':'||date_trunc('hour',clock_timestamp())::text)::uuid;
 insert into public.platform_events(id,actor,kind,message,details)
 values(identity,'research-autonomy','research-controller-maintenance-failed',
  'An optional controller maintenance check failed. The recorded fault is retained; ordinary claims still use their original admission and uncertainty guards.',p_details)
 on conflict(id) do nothing;
 return jsonb_build_object('recorded',true,'event_id',identity);
end$$;
revoke all on function public.research_autonomy_runtime_observe(text,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.research_autonomy_runtime_observe(text,jsonb) to service_role;
insert into public.platform_events(id,actor,kind,message,details) values(gen_random_uuid(),'interactive-release','research-controller-policy-compatibility',
 'The startup recovery RPC now accepts the deployed v2 turn policy. Original deadlines, budgets, unknown-call fences and scientific criteria are unchanged.',
 jsonb_build_object('version','research-controller-health-v1','turn_policy','autonomy-turn-policy-v2','ordinary_lease_guards_changed',false));
notify pgrst,'reload schema';
commit;
