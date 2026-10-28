begin;
-- Controller work includes source retrieval, dispatch admission, the native
-- window and artifact validation. Expiring at the Lambda timeout loses a late
-- completed response. Extend future task leases with the Lambda timeout;
-- existing unknown calls and historical receipts remain fenced and unchanged.
do $migration$ declare definition text;before text;begin
 definition=pg_get_functiondef('public.research_autonomy_before_confirmation(text,uuid,uuid,jsonb)'::regprocedure);
 before=$old$lease_until=clock_timestamp()+interval '300 seconds'$old$;
 if (length(definition)-length(replace(definition,before,'')))/length(before)<>1 then raise exception 'Unexpected controller lease window';end if;
 execute replace(definition,before,$new$lease_until=clock_timestamp()+interval '480 seconds'$new$);
 definition=pg_get_functiondef('public.research_model_dispatch(text,jsonb)'::regprocedure);
 before=$old$case when q.stage='building' then interval '240 seconds' else interval '240 seconds' end$old$;
 if (length(definition)-length(replace(definition,before,'')))/length(before)<>2 then raise exception 'Unexpected model admission windows';end if;
 definition=replace(definition,before,$new$case when q.stage='building' then interval '350 seconds' else interval '240 seconds' end$new$);
 before=$old$case when (select stage from public.research_autonomy_tasks where id=d.task_id)='building' then interval '245 seconds' else interval '235 seconds' end$old$;
 if strpos(definition,before)=0 then raise exception 'Unexpected model persistence fence';end if;
 execute replace(definition,before,$new$case when (select stage from public.research_autonomy_tasks where id=d.task_id)='building' then interval '330 seconds' else interval '235 seconds' end$new$);
end $migration$;
notify pgrst,'reload schema';
commit;
