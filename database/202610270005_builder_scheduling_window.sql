begin;
-- Headless startup and initial file inspection consumed a short slot before
-- an implementation response could be admitted. Extend only building dispatches;
-- preserve the existing 300-second controller task lease and all paper limits.
do $migration$ declare definition text;before text;begin
 definition=pg_get_functiondef('public.research_model_dispatch(text,jsonb)'::regprocedure);
 before=$old$q.lease_until>clock_timestamp()+interval '100 seconds'$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected model task lease gate';end if;
 definition=replace(definition,before,$new$q.lease_until>clock_timestamp()+case when q.stage='building' then interval '240 seconds' else interval '100 seconds' end$new$);
 before=$old$w.deadline_at>clock_timestamp()+interval '100 seconds'$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected model paper deadline gate';end if;
 definition=replace(definition,before,$new$w.deadline_at>clock_timestamp()+case when q.stage='building' then interval '240 seconds' else interval '100 seconds' end$new$);
 before=$old$lease_until=clock_timestamp()+interval '115 seconds'$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected model dispatch lease';end if;
 definition=replace(definition,before,$new$lease_until=clock_timestamp()+case when (select stage from public.research_autonomy_tasks where id=d.task_id)='building' then interval '245 seconds' else interval '115 seconds' end$new$);
 execute definition;
end $migration$;
notify pgrst,'reload schema';
commit;
