begin;
-- Version 3 stores experiments -> stages -> actionable substeps. Original flat
-- plans, confirmations, prompt versions and provider identities are untouched.
-- The common leaf checks retain exact source/claim coverage; hierarchy only
-- adds bounded organizational containers. No workers or experiments are started.
create or replace function public.research_valid_flat_experiment_plan(p jsonb,b jsonb) returns boolean language plpgsql immutable set search_path='' as $$
declare e jsonb;s jsonb;r text;refs text[];expected text[];covered text[]='{}';claims text[];checked text[]='{}';check_ref text;begin
 if jsonb_typeof(p) is distinct from 'object' or p-array['experiments']<>'{}'::jsonb or jsonb_typeof(p->'experiments') is distinct from 'array' then return false;end if;
 if jsonb_array_length(p->'experiments')>8 then return false;end if;
 select array_agg(v->>'ref') into refs from jsonb_each(public.research_experiment_plan_input(b)->'sections') t, jsonb_array_elements(t.value) v;
 select coalesce(array_agg('experiment-'||n),'{}'::text[]) into expected from jsonb_array_elements(b->'sections'->'experiment') with ordinality t(v,n);
 select coalesce(array_agg(v->>'ref'),'{}'::text[]) into claims from jsonb_array_elements(public.research_experiment_plan_input(b)->'sections'->'validate') v where v->>'kind'='claim';
 for e in select value from jsonb_array_elements(p->'experiments') loop
  if jsonb_typeof(e) is distinct from 'object' or e-array['title','experiment_refs','steps','open_questions']<>'{}'::jsonb or jsonb_typeof(e->'title') is distinct from 'string' or length(btrim(e->>'title')) not between 1 and 200 or
   jsonb_typeof(e->'experiment_refs') is distinct from 'array' or jsonb_typeof(e->'steps') is distinct from 'array' or jsonb_typeof(e->'open_questions') is distinct from 'array' then return false;end if;
  if jsonb_array_length(e->'experiment_refs') not between 1 and 8 or jsonb_array_length(e->'steps') not between 1 and 24 or jsonb_array_length(e->'open_questions')>12 then return false;end if;
  for r in select jsonb_array_elements_text(e->'experiment_refs') loop
   if r is null or not r=any(expected) or r=any(covered) then return false;end if;covered=array_append(covered,r);
  end loop;
  if exists(select 1 from jsonb_array_elements(e->'open_questions') q where jsonb_typeof(q)<>'string' or length(btrim(q#>>'{}')) not between 1 and 400) then return false;end if;
  for s in select value from jsonb_array_elements(e->'steps') loop
   if jsonb_typeof(s) is distinct from 'object' or s-array['title','instructions','basis','source_refs','validation_ref']<>'{}'::jsonb or jsonb_typeof(s->'title') is distinct from 'string' or length(btrim(s->>'title')) not between 1 and 160 or
    jsonb_typeof(s->'instructions') is distinct from 'string' or length(btrim(s->>'instructions')) not between 1 and 1200 or coalesce(s->>'basis','') not in ('paper','proposed') or jsonb_typeof(s->'source_refs') is distinct from 'array' then return false;end if;
   if jsonb_array_length(s->'source_refs')>32 or s->>'basis'='paper' and jsonb_array_length(s->'source_refs')=0 then return false;end if;
   if exists(select 1 from jsonb_array_elements(s->'source_refs') source_ref where jsonb_typeof(source_ref.value) is distinct from 'string') or
    exists(select 1 from jsonb_array_elements_text(s->'source_refs') source_ref where not source_ref.value=any(coalesce(refs,'{}'::text[]))) or
    (select count(*)<>count(distinct value) from jsonb_array_elements_text(s->'source_refs')) then return false;end if;
   check_ref=s->>'validation_ref';
   if check_ref is not null then
    if not check_ref=any(claims) or check_ref=any(checked) or not (s->'source_refs') ? check_ref then return false;end if;checked=array_append(checked,check_ref);
   end if;
  end loop;
 end loop;
 return cardinality(covered)=cardinality(expected) and (cardinality(expected)=0 or cardinality(checked)=cardinality(claims));
end$$;

create or replace function public.research_valid_experiment_plan(p jsonb,b jsonb) returns boolean
language plpgsql immutable set search_path='' as $$
declare e jsonb;stage jsonb;action jsonb;actions jsonb;experiments jsonb='[]';layout text;current_layout text;begin
 if jsonb_typeof(p) is distinct from 'object' or p-array['experiments']<>'{}'::jsonb or jsonb_typeof(p->'experiments') is distinct from 'array' then return false;end if;
 if jsonb_array_length(p->'experiments')>8 then return false;end if;
 for e in select value from jsonb_array_elements(p->'experiments') loop
  if jsonb_typeof(e) is distinct from 'object' then return false;end if;
  current_layout=case when e ? 'stages' then 'hierarchical' else 'flat' end;
  if layout is not null and layout<>current_layout then return false;end if;layout=current_layout;
  if current_layout='hierarchical' then
   if e-array['title','experiment_refs','stages','open_questions']<>'{}'::jsonb or jsonb_typeof(e->'stages') is distinct from 'array' then return false;end if;
   if jsonb_array_length(e->'stages') not between 1 and 8 then return false;end if;
   actions='[]'::jsonb;
   for stage in select value from jsonb_array_elements(e->'stages') loop
    if jsonb_typeof(stage) is distinct from 'object' or stage-array['title','steps']<>'{}'::jsonb or jsonb_typeof(stage->'title') is distinct from 'string' or
     length(btrim(stage->>'title')) not between 1 and 160 or jsonb_typeof(stage->'steps') is distinct from 'array' then return false;end if;
    if jsonb_array_length(stage->'steps') not between 1 and 8 then return false;end if;
    for action in select value from jsonb_array_elements(stage->'steps') loop
     if jsonb_typeof(action) is distinct from 'object' or not action ? 'validation_ref' or jsonb_typeof(action->'validation_ref') not in ('null','string') or
      jsonb_typeof(action->'instructions') is distinct from 'string' or length(btrim(action->>'instructions')) not between 1 and 800 then return false;end if;
    end loop;
    actions=actions||(stage->'steps');
   end loop;
   if jsonb_array_length(actions)>24 then return false;end if;
   experiments=experiments||jsonb_build_array((e-'stages')||jsonb_build_object('steps',actions));
  else
   -- Preserve the historical bound instead of expanding old flat contracts.
   if jsonb_typeof(e->'steps') is distinct from 'array' then return false;end if;
   if jsonb_array_length(e->'steps') not between 1 and 12 then return false;end if;
   experiments=experiments||jsonb_build_array(e);
  end if;
 end loop;
 return public.research_valid_flat_experiment_plan(jsonb_build_object('experiments',experiments),b);
end$$;

-- Explicit replacement preserves owner/Google checks, locked admissions,
-- original deadlines/budgets, immutable events and uncertain-call fences.
create or replace function public.research_experiment_plan(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare i public.research_paper_intakes;p public.research_experiment_plans;w public.research_autonomy_workflows;
 b jsonb;entry jsonb;original jsonb;section text;seen text[];spent bigint=0;calls bigint=0;request jsonb;configuration jsonb;template jsonb;content jsonb;hash text;prompt uuid;review_revision integer;review_breakdown jsonb;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or not exists(select 1 from auth.users u join auth.identities a on a.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and a.provider='google') then raise exception 'Verified Google owner required';end if;
 if public.research_assessment_deleted(p_study) then raise exception 'Assessment not found';end if;
 select * into i from public.research_paper_intakes where study_id=p_study for update;
 if i.study_id is null or i.owner_id<>p_actor or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper assessment not found';end if;
 select * into p from public.research_experiment_plans where study_id=p_study for update;
 if p.study_id is null then
  select revision,breakdown into review_revision,review_breakdown from public.research_paper_breakdown_reviews where study_id=p_study order by revision desc limit 1;
  if found then i.revision=review_revision;i.breakdown=review_breakdown;end if;
 end if;
 if p_operation='confirm' then
  if i.status<>'ready' then raise exception 'Phase one must be ready before confirmation';end if;
  b=p_payload->'confirmed_breakdown';
  if p.study_id is not null then
   if p.intake_revision is distinct from (p_payload->>'intake_revision')::integer or p.confirmed_breakdown is distinct from b then raise exception 'Phase one was already confirmed with different information';end if;
   return to_jsonb(p)||'{"admitted":false}'::jsonb;
  end if;
  if i.revision is distinct from (p_payload->>'intake_revision')::integer then raise exception 'The phase-one revision changed; reload and review it before confirming';end if;
  if jsonb_typeof(b) is distinct from 'object' or b-array['sections'] is distinct from i.breakdown-array['sections'] or jsonb_typeof(b->'sections') is distinct from 'object' or (b->'sections')-array['access','experiment','data','validate']<>'{}'::jsonb then raise exception 'Confirm the original four-section breakdown';end if;
  foreach section in array array['access','experiment','data','validate'] loop
   if jsonb_typeof(b->'sections'->section) is distinct from 'array' then raise exception 'Review all four sections';end if;
   seen='{}';
   for entry in select value from jsonb_array_elements(b->'sections'->section) loop
    select value into original from jsonb_array_elements(i.breakdown->'sections'->section) where value->>'id'=entry->>'id';
    if original is null or entry-array['description'] is distinct from original-array['description'] or jsonb_typeof(entry->'description') is distinct from 'string' or length(btrim(entry->>'description')) not between 1 and 400 or entry->>'id'=any(seen) then raise exception 'Only inclusion and descriptions may change; retain original quotes and PDF pages';end if;
    seen=array_append(seen,entry->>'id');
   end loop;
  end loop;
  if i.deadline_at<=clock_timestamp() then raise exception 'The original assessment deadline has expired';end if;
  request=nullif(p_payload->'request','null'::jsonb);
  if jsonb_array_length(b->'sections'->'experiment')=0 then
   if request is not null then raise exception 'No model call is needed when no experiments are confirmed';end if;
   insert into public.research_experiment_plans(study_id,owner_id,intake_revision,confirmed_breakdown,deadline_at,status,plan,reason,reserved_cents,model_calls)
    values(p_study,p_actor,i.revision,b,i.deadline_at,'ready','{"experiments":[]}','No experiments were included in the confirmed sections.',0,0) returning * into p;
   return to_jsonb(p)||'{"admitted":false}'::jsonb;
  end if;
  if jsonb_typeof(request) is distinct from 'object' or request->>'model' is distinct from 'gpt-5.4-mini-2026-03-17' or request->'background' is distinct from 'true'::jsonb or request->'store' is distinct from 'true'::jsonb or
   jsonb_typeof(request->'instructions') is distinct from 'string' or length(request->>'instructions') not between 1 and 40000 or jsonb_typeof(request->'input') is distinct from 'string' or
   octet_length(request::text)>160000 or exists(select 1 from jsonb_object_keys(request) k where k not in ('model','instructions','input','background','store','reasoning','max_output_tokens','text')) then raise exception 'A bounded server-side planning request is required';end if;
  if (request->>'input')::jsonb is distinct from public.research_experiment_plan_input(b) or coalesce(request->'text'->'format'->>'name','') not in ('paper_experiment_steps_v1','paper_experiment_steps_v2','paper_experiment_steps_v3') then raise exception 'Plan only from the exact confirmed sections';end if;
  select * into w from public.research_autonomy_workflows where study_id=p_study;
  if found then
   spent=w.committed_cents;select coalesce(sum(attempts),0) into calls from public.research_autonomy_tasks where study_id=p_study;
   if w.max_spend_cents is not null and spent+i.reserved_cents+100>w.max_spend_cents then raise exception 'The original assessment spending limit does not admit planning';end if;
  end if;
  if not public.autonomy_budget_allows('research_assessment',spent+i.reserved_cents,calls+i.model_calls,100,1) then raise exception 'The assessment budget does not admit this planning call';end if;
  insert into public.research_experiment_plans(study_id,owner_id,intake_revision,confirmed_breakdown,deadline_at,status,submit_token,request,reserved_cents,model_calls,policy_snapshot,reason)
   values(p_study,p_actor,i.revision,b,i.deadline_at,'submitting',gen_random_uuid(),request,100,1,public.autonomy_assessment_budget_terms(),'Submitting experiment implementation planning.') returning * into p;
  -- Catalogue only a generic template/configuration. The confirmed content,
  -- full request, response and usage remain private and linked to this study.
  configuration=request-array['input','instructions'];
  template='{"phase":"confirmed-paper-breakdown-v1","sections":{"access":"{{confirmed_access_details_with_source_quotes}}","experiment":"{{confirmed_experiment_details_with_source_quotes}}","data":"{{confirmed_data_details_with_source_quotes}}","validate":"{{confirmed_validate_details_with_source_quotes}}"}}'::jsonb;
  content=jsonb_build_object('instructions',request->>'instructions','input_template',template,'request_configuration',configuration);
  hash=encode(sha256(convert_to(content::text,'UTF8')),'hex');
  insert into public.research_paper_prompt_versions(version,instructions,input_template,request_configuration,content_sha256,created_at)
   values('paper-assessment-'||hash,request->>'instructions',template,configuration,hash,p.confirmed_at) on conflict(content_sha256) do nothing;
  select id into strict prompt from public.research_paper_prompt_versions where content_sha256=hash;
  insert into public.research_experiment_plan_prompt_uses values(p_study,prompt,encode(sha256(convert_to(request::text,'UTF8')),'hex'),p.confirmed_at);
  return to_jsonb(p)||'{"admitted":true}'::jsonb;
 end if;
 if p.study_id is null then raise exception 'Confirm phase one before planning';end if;
 if p.submit_token is distinct from (p_payload->>'token')::uuid then raise exception 'Original planning call token required';end if;
 if p_operation='submitted' then
  if p.provider_response_id is not null then
   if p.provider_response_id is distinct from p_payload->>'response_id' then raise exception 'Original provider identity cannot change';end if;return to_jsonb(p);
  end if;
  if p.status not in ('submitting','uncertain') or coalesce(p_payload->>'response_id','') !~ '^resp_[A-Za-z0-9_-]{1,200}$' then raise exception 'Original submitting planning call required';end if;
  update public.research_experiment_plans set status='processing',provider_response_id=p_payload->>'response_id',response=p_payload->'response',reason='Preparing implementation steps.' where study_id=p_study returning * into p;return to_jsonb(p);
 end if;
 if p.status in ('ready','failed','cancelled') then return to_jsonb(p);end if;
 if p_operation='uncertain' then
  if p.provider_response_id is not null then return to_jsonb(p);end if;
  update public.research_experiment_plans set status='uncertain',reason=left(p_payload->>'reason',2000) where study_id=p_study returning * into p;return to_jsonb(p);
 end if;
 if p_operation='finish' then
  if p.status<>'processing' or p.provider_response_id is distinct from p_payload->>'response_id' or p_payload->'response'->>'id' is distinct from p.provider_response_id or p_payload->'response'->>'status' is distinct from 'completed' or not public.research_valid_experiment_plan(p_payload->'plan',p.confirmed_breakdown) or
   (p.request->'text'->'format'->>'name'='paper_experiment_steps_v3' and exists(select 1 from jsonb_array_elements(p_payload->'plan'->'experiments') e where not e ? 'stages')) or
   (p.request->'text'->'format'->>'name' in ('paper_experiment_steps_v1','paper_experiment_steps_v2') and exists(select 1 from jsonb_array_elements(p_payload->'plan'->'experiments') e where e ? 'stages')) then raise exception 'Verified original response and complete source-bound plan required';end if;
  update public.research_experiment_plans set status='ready',plan=p_payload->'plan',response=p_payload->'response',reason=null where study_id=p_study returning * into p;return to_jsonb(p);
 end if;
 if p_operation in ('failed','cancel') then
  if p_operation='cancel' and (p.provider_response_id is null or p_payload->'response'->>'id' is distinct from p.provider_response_id or p_payload->'response'->>'status' is distinct from 'cancelled') then raise exception 'Confirmed provider cancellation required';end if;
  if p.status='uncertain' then raise exception 'Reconcile the uncertain provider call before stopping';end if;
  update public.research_experiment_plans set status=case when p_operation='cancel' then 'cancelled' else 'failed' end,response=coalesce(p_payload->'response',response),reason=left(p_payload->>'reason',2000) where study_id=p_study returning * into p;return to_jsonb(p);
 end if;
 raise exception 'Unknown experiment planning operation';
end$$;

revoke all on function public.research_valid_flat_experiment_plan(jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.research_valid_flat_experiment_plan(jsonb,jsonb) to service_role;
revoke all on function public.research_valid_experiment_plan(jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.research_valid_experiment_plan(jsonb,jsonb) to service_role;
revoke all on function public.research_experiment_plan(text,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.research_experiment_plan(text,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
