begin;

-- A phase-two plan is private, owner-confirmed planning. No task, queue job or
-- worker dispatch is created by this migration or RPC.
create table public.research_experiment_plans (
 study_id uuid primary key references public.research_paper_intakes(study_id), owner_id uuid not null,
 intake_revision integer not null, confirmed_at timestamptz not null default clock_timestamp(),
 confirmed_breakdown jsonb not null, deadline_at timestamptz not null,
 status text not null check(status in ('submitting','processing','uncertain','ready','failed','cancelled')),
 submit_token uuid, provider_response_id text unique, request jsonb, response jsonb, plan jsonb, reason text,
 reserved_cents integer not null check(reserved_cents in (0,100)), model_calls integer not null check(model_calls in (0,1)), policy_snapshot jsonb,
 updated_at timestamptz not null default clock_timestamp(), revision integer not null default 1,
 check(status<>'ready' or plan is not null),
 check(provider_response_id is null or provider_response_id ~ '^resp_[A-Za-z0-9_-]{1,200}$')
);
create table public.research_experiment_plan_events (
 id bigint generated always as identity primary key, study_id uuid not null references public.research_experiment_plans(study_id),
 revision integer not null, snapshot jsonb not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,revision)
);
create table public.research_experiment_plan_prompt_uses (
 study_id uuid primary key references public.research_experiment_plans(study_id),
 prompt_version_id uuid not null references public.research_paper_prompt_versions(id),
 request_sha256 text not null check(request_sha256 ~ '^[a-f0-9]{64}$'), recorded_at timestamptz not null
);
alter table public.research_experiment_plans enable row level security;
alter table public.research_experiment_plan_events enable row level security;
alter table public.research_experiment_plan_prompt_uses enable row level security;
revoke all on public.research_experiment_plans,public.research_experiment_plan_events,public.research_experiment_plan_prompt_uses from public,anon,authenticated,service_role;
grant select on public.research_experiment_plans,public.research_experiment_plan_events,public.research_experiment_plan_prompt_uses to service_role;
create trigger assessment_active before insert or update on public.research_experiment_plans for each row execute function public.research_require_active_assessment();
create trigger assessment_active before insert or update on public.research_experiment_plan_events for each row execute function public.research_require_active_assessment();
create trigger assessment_active before insert or update on public.research_experiment_plan_prompt_uses for each row execute function public.research_require_active_assessment();
create trigger plan_events_immutable before update or delete on public.research_experiment_plan_events for each row execute function public.research_immutable();
create trigger plan_prompt_use_immutable before update or delete on public.research_experiment_plan_prompt_uses for each row execute function public.research_immutable();

create function public.research_experiment_plan_history() returns trigger language plpgsql set search_path='' as $$begin
 if tg_op='DELETE' then raise exception 'Retain confirmed paper and planning history';end if;
 if tg_op='UPDATE' then
  if (new.study_id,new.owner_id,new.intake_revision,new.confirmed_at,new.confirmed_breakdown,new.deadline_at,new.request,new.submit_token,new.reserved_cents,new.model_calls,new.policy_snapshot)
   is distinct from (old.study_id,old.owner_id,old.intake_revision,old.confirmed_at,old.confirmed_breakdown,old.deadline_at,old.request,old.submit_token,old.reserved_cents,old.model_calls,old.policy_snapshot)
   or old.status in ('ready','failed','cancelled') or old.provider_response_id is not null and new.provider_response_id is distinct from old.provider_response_id
  then raise exception 'Original confirmation, prompt, limits and provider identity are immutable';end if;
  new.revision=old.revision+1;new.updated_at=clock_timestamp();
 end if;
 return new;
end$$;
create trigger plan_history before insert or update or delete on public.research_experiment_plans for each row execute function public.research_experiment_plan_history();
create function public.research_experiment_plan_audit() returns trigger language plpgsql set search_path='' as $$begin
 insert into public.research_experiment_plan_events(study_id,revision,snapshot) values(new.study_id,new.revision,to_jsonb(new));return new;
end$$;
create trigger plan_audit after insert or update on public.research_experiment_plans for each row execute function public.research_experiment_plan_audit();

-- Exactly the input assembled by Next.js, with neutral references instead of
-- original UUIDs. Only this private input contains the reviewed paper text.
create function public.research_experiment_plan_input(b jsonb) returns jsonb language sql immutable set search_path='' as $$
 select jsonb_build_object('phase','confirmed-paper-breakdown-v1','sections',jsonb_object_agg(section,
  coalesce((select jsonb_agg(jsonb_build_object('ref',section||'-'||n,'description',entry->'description','quote',entry->'quote','page',entry->'page') order by n)
   from jsonb_array_elements(b->'sections'->section) with ordinality e(entry,n)),'[]'::jsonb)))
 from unnest(array['access','experiment','data','validate']) section
$$;

-- Defence in depth: the service verifies output in TypeScript; the database
-- also rejects invented references, omissions and duplicate experiment coverage.
create function public.research_valid_experiment_plan(p jsonb,b jsonb) returns boolean language plpgsql immutable set search_path='' as $$
declare e jsonb;s jsonb;r text;refs text[];expected text[];covered text[]='{}';begin
 if jsonb_typeof(p) is distinct from 'object' or p-array['experiments']<>'{}'::jsonb or jsonb_typeof(p->'experiments') is distinct from 'array' then return false;end if;
 if jsonb_array_length(p->'experiments')>8 then return false;end if;
 select array_agg(v->>'ref') into refs from jsonb_each(public.research_experiment_plan_input(b)->'sections') t, jsonb_array_elements(t.value) v;
 select coalesce(array_agg('experiment-'||n),'{}'::text[]) into expected from jsonb_array_elements(b->'sections'->'experiment') with ordinality t(v,n);
 for e in select value from jsonb_array_elements(p->'experiments') loop
  if jsonb_typeof(e) is distinct from 'object' or e-array['title','experiment_refs','steps','open_questions']<>'{}'::jsonb or jsonb_typeof(e->'title') is distinct from 'string' or length(btrim(e->>'title')) not between 1 and 200 or
   jsonb_typeof(e->'experiment_refs') is distinct from 'array' or jsonb_typeof(e->'steps') is distinct from 'array' or jsonb_typeof(e->'open_questions') is distinct from 'array' then return false;end if;
  if jsonb_array_length(e->'experiment_refs') not between 1 and 8 or jsonb_array_length(e->'steps') not between 1 and 12 or jsonb_array_length(e->'open_questions')>12 then return false;end if;
  for r in select jsonb_array_elements_text(e->'experiment_refs') loop
   if r is null or not r=any(expected) or r=any(covered) then return false;end if;covered=array_append(covered,r);
  end loop;
  if exists(select 1 from jsonb_array_elements(e->'open_questions') q where jsonb_typeof(q)<>'string' or length(btrim(q#>>'{}')) not between 1 and 400) then return false;end if;
  for s in select value from jsonb_array_elements(e->'steps') loop
   if jsonb_typeof(s) is distinct from 'object' or s-array['title','instructions','basis','source_refs']<>'{}'::jsonb or jsonb_typeof(s->'title') is distinct from 'string' or length(btrim(s->>'title')) not between 1 and 160 or
    jsonb_typeof(s->'instructions') is distinct from 'string' or length(btrim(s->>'instructions')) not between 1 and 1200 or coalesce(s->>'basis','') not in ('paper','proposed') or jsonb_typeof(s->'source_refs') is distinct from 'array' then return false;end if;
   if jsonb_array_length(s->'source_refs')>32 or s->>'basis'='paper' and jsonb_array_length(s->'source_refs')=0 then return false;end if;
   if exists(select 1 from jsonb_array_elements_text(s->'source_refs') source_ref where not source_ref.value=any(coalesce(refs,'{}'::text[]))) or
    (select count(*)<>count(distinct value) from jsonb_array_elements_text(s->'source_refs')) then return false;end if;
  end loop;
 end loop;
 return cardinality(covered)=cardinality(expected);
end$$;

create function public.research_experiment_plan(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare i public.research_paper_intakes;p public.research_experiment_plans;w public.research_autonomy_workflows;
 b jsonb;entry jsonb;original jsonb;section text;seen text[];spent bigint=0;calls bigint=0;request jsonb;configuration jsonb;template jsonb;content jsonb;hash text;prompt uuid;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or not exists(select 1 from auth.users u join auth.identities a on a.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and a.provider='google') then raise exception 'Verified Google owner required';end if;
 if public.research_assessment_deleted(p_study) then raise exception 'Assessment not found';end if;
 select * into i from public.research_paper_intakes where study_id=p_study for update;
 if i.study_id is null or i.owner_id<>p_actor or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper assessment not found';end if;
 select * into p from public.research_experiment_plans where study_id=p_study for update;
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
  if (request->>'input')::jsonb is distinct from public.research_experiment_plan_input(b) or request->'text'->'format'->>'name' is distinct from 'paper_experiment_steps_v1' then raise exception 'Plan only from the exact confirmed sections';end if;
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
  if p.status<>'processing' or p.provider_response_id is distinct from p_payload->>'response_id' or p_payload->'response'->>'id' is distinct from p.provider_response_id or p_payload->'response'->>'status' is distinct from 'completed' or not public.research_valid_experiment_plan(p_payload->'plan',p.confirmed_breakdown) then raise exception 'Verified original response and complete source-bound plan required';end if;
  update public.research_experiment_plans set status='ready',plan=p_payload->'plan',response=p_payload->'response',reason=null where study_id=p_study returning * into p;return to_jsonb(p);
 end if;
 if p_operation in ('failed','cancel') then
  if p_operation='cancel' and (p.provider_response_id is null or p_payload->'response'->>'id' is distinct from p.provider_response_id or p_payload->'response'->>'status' is distinct from 'cancelled') then raise exception 'Confirmed provider cancellation required';end if;
  if p.status='uncertain' then raise exception 'Reconcile the uncertain provider call before stopping';end if;
  update public.research_experiment_plans set status=case when p_operation='cancel' then 'cancelled' else 'failed' end,response=coalesce(p_payload->'response',response),reason=left(p_payload->>'reason',2000) where study_id=p_study returning * into p;return to_jsonb(p);
 end if;
 raise exception 'Unknown experiment planning operation';
end$$;

-- Keep the existing owner deletion API, and serialize its new planning fence
-- with confirmation/cancellation under the same assessment advisory lock.
create function public.research_plan_deletion_guard() returns trigger language plpgsql security definer set search_path='' as $$begin
 if old.deleted_at is null and new.deleted_at is not null then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  if exists(select 1 from public.research_experiment_plans where study_id=new.id and (status in ('submitting','processing','uncertain') or response->>'status' in ('queued','in_progress','cancelling'))) then raise exception 'Cancel or reconcile the active experiment planning call before deleting this assessment' using errcode='55000';end if;
 end if;return new;
end$$;
create trigger plan_deletion_guard before update of deleted_at on public.research_studies for each row execute function public.research_plan_deletion_guard();
revoke all on function public.research_experiment_plan(text,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.research_experiment_plan(text,uuid,uuid,jsonb) to service_role;
revoke all on function public.research_experiment_plan_history(),public.research_experiment_plan_audit(),public.research_experiment_plan_input(jsonb),public.research_valid_experiment_plan(jsonb,jsonb),public.research_plan_deletion_guard() from public,anon,authenticated,service_role;
notify pgrst,'reload schema';
commit;
