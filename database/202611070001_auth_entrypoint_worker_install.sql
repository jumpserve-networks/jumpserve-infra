begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
-- Extend only the fixed qualification-profile allowlist. Original operation,
-- source, certificate, cancellation, deadline, drain and receipt checks remain.
do $migration$ declare definition text;old_clause text;new_clause text;begin
 definition=pg_get_functiondef('public.research_runtime_worker_install(uuid,text,uuid)'::regprocedure);
 old_clause=$old$or t.checkpoint->'research_runtime'->'scope'->>'qualification_profile' is distinct from 'captured-provider-failures-v1'$old$;
 new_clause=$new$or coalesce(t.checkpoint->'research_runtime'->'scope'->>'qualification_profile','') not in ('captured-provider-failures-v1','auth-helper-entrypoint-v1')$new$;
 if (length(definition)-length(replace(definition,old_clause,'')))/length(old_clause)<>1 then raise exception 'Frozen worker profile guard differs';end if;
 execute replace(definition,old_clause,new_clause);
end $migration$;
notify pgrst,'reload schema';
commit;
