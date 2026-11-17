begin;
-- Accept the new full-model planning profile. Older pinned requests remain
-- admissible during rollout/rollback; immutable existing calls are unchanged.
do $$declare definition text;updated text;begin
 definition=pg_get_functiondef('public.research_experiment_plan(text,uuid,uuid,jsonb)'::regprocedure);
 updated=replace(definition,$old$request->>'model' is distinct from 'gpt-5.4-mini-2026-03-17'$old$,$new$coalesce(request->>'model','') not in ('gpt-5.4-mini-2026-03-17','gpt-5.4-2026-03-05')$new$);
 if updated=definition and position($new$coalesce(request->>'model','') not in ('gpt-5.4-mini-2026-03-17','gpt-5.4-2026-03-05')$new$ in definition)=0 then raise exception 'Unexpected planning admission implementation';end if;
 execute updated;
end$$;
revoke all on function public.research_experiment_plan(text,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.research_experiment_plan(text,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
