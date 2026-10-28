begin;
-- A retained HTTP200 stream exceeded the former 65-second total response
-- deadline. Enlarge the data-only window and its fences together, without
-- changing paper limits, existing dispatches, requests or unknown outcomes.
do $migration$ declare definition text;before text;begin
 definition=pg_get_functiondef('public.research_model_dispatch(text,jsonb)'::regprocedure);
 before=$old$case when q.stage='building' then interval '240 seconds' else interval '100 seconds' end$old$;
 if (length(definition)-length(replace(definition,before,'')))/length(before)<>2 then raise exception 'Unexpected model admission windows';end if;
 definition=replace(definition,before,$new$case when q.stage='building' then interval '240 seconds' else interval '240 seconds' end$new$);
 before=$old$case when (select stage from public.research_autonomy_tasks where id=d.task_id)='building' then interval '245 seconds' else interval '115 seconds' end$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected model dispatch fence';end if;
 definition=replace(definition,before,$new$case when (select stage from public.research_autonomy_tasks where id=d.task_id)='building' then interval '245 seconds' else interval '235 seconds' end$new$);
 execute definition;
end $migration$;
notify pgrst,'reload schema';
commit;
