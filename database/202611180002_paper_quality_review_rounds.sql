begin;
-- Allow three repairs, each followed by a fresh review. Keep all original
-- admissions, provider identities, evidence, approvals, budgets and deadlines.
alter table public.research_paper_quality_workflows
 drop constraint research_paper_quality_workflows_round_check,
 add constraint research_paper_quality_workflows_round_check check(round between 0 and 3);
alter table public.research_paper_quality_calls
 drop constraint research_paper_quality_calls_position_check,
 drop constraint research_paper_quality_calls_check,
 add constraint research_paper_quality_calls_position_check check(position between 1 and 7),
 add constraint research_paper_quality_calls_check check((kind='repair')=(position%2=0));

-- Patch only the round/call bounds in the qualified control function. Refuse
-- unexpected definitions instead of replacing its scientific/privacy guards.
do $$
declare body text;old_text text;new_text text;patch jsonb;begin
 select prosrc into strict body from pg_proc
 where oid='public.research_paper_quality_control(text,uuid,uuid,jsonb)'::regprocedure;
 for patch in select value from jsonb_array_elements(jsonb_build_array(
  jsonb_build_array(
   $old$position=case when w.status='repair_pending' then 2 when w.round=1 then 3 else 1 end;$old$,
   $new$position=2*w.round+case when w.status='repair_pending' then 2 else 1 end;$new$),
  jsonb_build_array(
   $old$case when position=2 then 'repair' else 'review' end$old$,
   $new$case when position%2=0 then 'repair' else 'review' end$new$),
  jsonb_build_array(
   $old$phase=case when position=2 then 'repairing'$old$,
   $new$phase=case when position%2=0 then 'repairing'$new$),
  jsonb_build_array(
   $old$c.kind<>'repair' or c.position<>2 or not public.research_valid_quality_candidate$old$,
   $new$c.kind<>'repair' or w.round>=3 or c.position<>2*(w.round+1) or not public.research_valid_quality_candidate$new$),
  jsonb_build_array(
   $old$checks=checks,round=1,status='review_pending'$old$,
   $new$checks=checks,round=w.round+1,status='review_pending'$new$),
  jsonb_build_array(
   $old$elsif w.round=0 then update public.research_paper_quality_workflows$old$,
   $new$elsif w.round<3 then update public.research_paper_quality_workflows$new$),
  jsonb_build_array(
   $old$reason='Review found issues. One bounded repair will be reviewed again.'$old$,
   $new$reason=format('Review found issues. Repair round %s of 3 will be reviewed again.',w.round+1)$new$),
  jsonb_build_array(
   $old$reason='Issues remain after the single repair and independent re-review.'$old$,
   $new$reason='Issues remain after three repair rounds and independent re-reviews.'$new$)
 )) loop
  old_text=patch->>0;new_text=patch->>1;
  if position(old_text in body)>0 then
   if length(body)-length(replace(body,old_text,''))<>length(old_text) then raise exception 'Review round migration needs one exact original control anchor';end if;
   body=replace(body,old_text,new_text);
  elsif position(new_text in body)=0 then raise exception 'The current quality control needs explicit review before widening repair rounds';
  end if;
 end loop;
 execute 'create or replace function public.research_paper_quality_control(p_operation text,p_actor uuid,p_workflow uuid,p_payload jsonb default ''{}'') returns jsonb language plpgsql security definer set search_path='''' as '||quote_literal(body);
end$$;
revoke all on function public.research_paper_quality_control(text,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
grant execute on function public.research_paper_quality_control(text,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
