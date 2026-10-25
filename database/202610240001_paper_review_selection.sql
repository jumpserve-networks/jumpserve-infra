begin;

-- Reuse the private, revisioned review/event relations. Original claim rows,
-- historical selections and experiment evidence remain immutable.
alter function public.research_paper_review(text,uuid,uuid,jsonb) rename to research_paper_review_before_selection;
create function public.research_paper_review(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.research_paper_reviews; w public.research_autonomy_workflows; t public.research_autonomy_tasks;
 s jsonb; ids jsonb; original_revision integer; result jsonb;
begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper review not found'; end if;
 select * into strict r from public.research_paper_reviews where study_id=p_study for update;
 if p_operation='organize' then
  if p_payload<>'{}'::jsonb then raise exception 'Organization cannot change paper authorization'; end if;
  if r.status='preparing' and r.metadata->'selection'->>'version'='paper-review-selection-v1' then return to_jsonb(r); end if;
  if r.status not in ('ready','failed') or jsonb_array_length(r.seeds)=0 then raise exception 'Only an unconfirmed retained candidate inventory can be organized'; end if;
  select * into strict w from public.research_autonomy_workflows where study_id=p_study for update;
  if w.status in ('cancelled','budget','deadline') or w.deadline_at<=clock_timestamp()+interval '180 seconds' or w.committed_cents+5>w.max_spend_cents then raise exception 'Original paper authorization cannot admit organization'; end if;
  select * into strict t from public.research_autonomy_tasks where study_id=p_study and claim_id is null for update;
  if t.status='running' or exists(select 1 from public.research_autonomy_turns where task_id=t.id and status in ('running','unknown')) then raise exception 'Reconcile the active preparation invocation before organizing'; end if;
  update public.research_paper_reviews set status='preparing',metadata=metadata||jsonb_build_object('selection',jsonb_build_object('version','paper-review-selection-v1','status','preparing','cursor',0)),revision=revision+1,updated_at=clock_timestamp() where study_id=p_study returning * into r;
  update public.research_autonomy_tasks set status='queued',context=(context-'review_selection'-'selection_failure')||'{"organize_existing_only":true}',reason='Organizing retained statements into central claims and testable findings; original authorization is unchanged.',lease_token=null,lease_until=null,next_at=clock_timestamp(),updated_at=clock_timestamp() where id=t.id;
  update public.research_autonomy_workflows set status='running',reason='Owner requested organization of the retained paper inventory.',updated_at=clock_timestamp() where study_id=p_study;
  return to_jsonb(r);
 end if;
 if p_operation='organization' then
  select * into strict t from public.research_autonomy_tasks where id=(p_payload->>'task_id')::uuid and study_id=p_study and claim_id is null;
  if r.status<>'preparing' or t.status<>'running' or t.lease_token is distinct from (p_payload->>'token')::uuid or t.lease_until<=clock_timestamp() then raise exception 'Current preparation lease required'; end if;
  s=p_payload->'selection';
  if s->>'version' is distinct from 'paper-review-selection-v1' or coalesce(s->>'status','') not in ('preparing','ready') or
   jsonb_typeof(s->'cursor') is distinct from 'number' or jsonb_typeof(s->'candidate_count') is distinct from 'number' or
   jsonb_typeof(s->'central_claims') is distinct from 'array' or jsonb_typeof(s->'testable_findings') is distinct from 'array' then raise exception 'Versioned review groups required'; end if;
  if jsonb_array_length(s->'central_claims')>3 or jsonb_array_length(s->'testable_findings')>15 or
   (s->>'candidate_count')::integer<>jsonb_array_length(r.seeds) or (s->>'cursor')::integer not between 1 and jsonb_array_length(r.seeds) or
   (s->>'cursor')::integer<coalesce((r.metadata->'selection'->>'cursor')::integer,0) or
   (s->>'status'='ready') is distinct from ((s->>'cursor')::integer=jsonb_array_length(r.seeds)) then raise exception 'Invalid organization coverage or shortlist bounds'; end if;
  select coalesce(jsonb_agg(v->>'claim_id'),'[]') into ids from jsonb_array_elements((s->'central_claims')||(s->'testable_findings')) v;
  if (select count(distinct value) from jsonb_array_elements_text(ids))<>jsonb_array_length(ids) or exists(select 1 from jsonb_array_elements_text(ids) c where not exists(select 1 from jsonb_array_elements(r.seeds) seed where seed->>'claim_id'=c)) or
   exists(select 1 from jsonb_array_elements((s->'central_claims')||(s->'testable_findings')) v where jsonb_typeof(v->'label') is distinct from 'string' or length(btrim(v->>'label')) not between 1 and 160) then raise exception 'Review groups require unique retained statement IDs and bounded labels'; end if;
  update public.research_paper_reviews set metadata=metadata||jsonb_build_object('selection',s),revision=revision+1,updated_at=clock_timestamp() where study_id=p_study returning * into r;
  return to_jsonb(r);
 end if;
 if p_operation='confirm' and p_payload ? 'selection' then
  s=p_payload->'selection';
  if jsonb_typeof(s) is distinct from 'object' or (select count(*) from jsonb_object_keys(s))<>2 or
   jsonb_typeof(s->'central_claims') is distinct from 'array' or jsonb_typeof(s->'testable_findings') is distinct from 'array' then raise exception 'Select central claims and testable findings separately'; end if;
  select coalesce(jsonb_agg(value order by value),'[]') into ids from jsonb_array_elements_text((s->'central_claims')||(s->'testable_findings'));
  if jsonb_array_length(ids) not between 1 and 200 or (select count(distinct value) from jsonb_array_elements_text(ids))<>jsonb_array_length(ids) or
   ids is distinct from (select coalesce(jsonb_agg(value order by value),'[]') from jsonb_array_elements_text(p_payload->'claim_ids')) then raise exception 'Selected groups must exactly match unique assessment claim IDs'; end if;
  -- Canonicalize group order for safe retries without changing recorded IDs.
  s=jsonb_build_object('central_claims',(select coalesce(jsonb_agg(value order by value),'[]') from jsonb_array_elements_text(s->'central_claims')),
   'testable_findings',(select coalesce(jsonb_agg(value order by value),'[]') from jsonb_array_elements_text(s->'testable_findings')));
  if r.status='confirmed' then
   if r.metadata->'owner_selection' is distinct from s or (r.metadata->>'owner_selection_review_revision')::integer is distinct from (p_payload->>'revision')::integer then raise exception 'This assessment already has a different confirmed selection'; end if;
   return public.research_paper_review_before_selection('confirm',p_actor,p_study,(p_payload-'selection')||jsonb_build_object('revision',r.confirmation->'review_revision'));
  end if;
  if r.status<>'ready' or r.revision is distinct from (p_payload->>'revision')::integer then raise exception 'Paper preparation changed or is incomplete; reload the review'; end if;
  original_revision=r.revision;
  update public.research_paper_reviews set metadata=metadata||jsonb_build_object('owner_selection',s,'owner_selection_review_revision',original_revision),revision=revision+1,updated_at=clock_timestamp() where study_id=p_study returning * into r;
  result=public.research_paper_review_before_selection('confirm',p_actor,p_study,(p_payload-'selection')||jsonb_build_object('revision',r.revision));
  return result;
 end if;
 return public.research_paper_review_before_selection(p_operation,p_actor,p_study,p_payload);
end $$;
revoke all on function public.research_paper_review_before_selection(text,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
revoke all on function public.research_paper_review(text,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.research_paper_review(text,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
