begin;
-- Add a managed repair runtime; preserve every existing Responses call, source,
-- approval, cancellation, reservation and deadline. No historical work is reopened.
alter table public.research_paper_quality_calls add column if not exists provider_type text not null default 'responses' check(provider_type in ('responses','managed_agent'));
create table if not exists public.research_paper_agent_sessions (
 call_id uuid primary key references public.research_paper_quality_calls(id),
 workflow_id uuid not null references public.research_paper_quality_workflows(id),study_id uuid not null,owner_id uuid not null,submit_token uuid not null,
 status text not null default 'preparing' check(status in ('preparing','submitting','processing','uncertain','completed','failed','cancelled')),
 provider_session_id text unique check(provider_session_id ~ '^sess_[A-Za-z0-9_-]{1,200}$'),request jsonb,
 initial_candidate jsonb not null,candidate jsonb not null,candidate_version integer not null default 0 check(candidate_version between 0 and 24),
 session jsonb,turn jsonb,cancel_requested_at timestamptz,deadline_at timestamptz not null,
 created_at timestamptz not null default clock_timestamp(),updated_at timestamptz not null default clock_timestamp()
);
create table if not exists public.research_paper_agent_actions (
 id uuid primary key default gen_random_uuid(),call_id uuid not null references public.research_paper_agent_sessions(call_id),workflow_id uuid not null,study_id uuid not null,owner_id uuid not null,
 position integer not null check(position between 1 and 24),repair_round integer not null check(repair_round between 1 and 3),turn_id text not null,provider_call_id text not null,
 name text not null check(name in ('read_evidence','apply_patch','run_validator','record_platform_issue')),arguments jsonb not null,
 status text not null default 'claimed' check(status in ('claimed','completed')),lease_token uuid not null default gen_random_uuid(),lease_until timestamptz not null,
 candidate_version integer not null,result jsonb,checks jsonb,
 created_at timestamptz not null default clock_timestamp(),completed_at timestamptz,
 unique(call_id,turn_id,provider_call_id),unique(call_id,position)
);
create table if not exists public.research_paper_agent_events (
 id bigint generated always as identity primary key,call_id uuid not null references public.research_paper_agent_sessions(call_id),workflow_id uuid not null,study_id uuid not null,
 kind text not null,snapshot jsonb not null,created_at timestamptz not null default clock_timestamp()
);
create table if not exists public.research_paper_agent_items (
 call_id uuid not null references public.research_paper_agent_sessions(call_id),item_key text not null,
 content_sha256 text not null check(content_sha256 ~ '^[a-f0-9]{64}$'),data jsonb not null,created_at timestamptz not null default clock_timestamp(),primary key(call_id,item_key)
);
create table if not exists public.research_paper_agent_prompt_uses (
 call_id uuid primary key references public.research_paper_agent_sessions(call_id),study_id uuid not null,prompt_version_id uuid not null references public.research_paper_prompt_versions(id),request_sha256 text not null,created_at timestamptz not null default clock_timestamp()
);
create index if not exists paper_agent_owner_actions on public.research_paper_agent_actions(workflow_id,owner_id,call_id,position);
create index if not exists paper_agent_pending on public.research_paper_agent_sessions(status,updated_at);
do $$declare t text;begin
 foreach t in array array['research_paper_agent_sessions','research_paper_agent_actions','research_paper_agent_events','research_paper_agent_items','research_paper_agent_prompt_uses'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role',t);
  execute format('grant select on public.%I to service_role',t);
 end loop;
 foreach t in array array['research_paper_agent_events','research_paper_agent_items','research_paper_agent_prompt_uses'] loop
  execute format('drop trigger if exists paper_agent_immutable on public.%I',t);
  execute format('create trigger paper_agent_immutable before update or delete on public.%I for each row execute function public.research_immutable()',t);
 end loop;
end$$;
create or replace function public.research_paper_agent_history_guard() returns trigger language plpgsql set search_path='' as $$begin
 if tg_op='DELETE' then raise exception 'Retain managed repair history';end if;
 if tg_table_name='research_paper_quality_calls' then
  if new.provider_type is distinct from old.provider_type then raise exception 'The original provider runtime is immutable';end if;
 elsif tg_table_name='research_paper_agent_sessions' then
  if (new.call_id,new.workflow_id,new.study_id,new.owner_id,new.submit_token,new.initial_candidate,new.deadline_at,new.created_at) is distinct from (old.call_id,old.workflow_id,old.study_id,old.owner_id,old.submit_token,old.initial_candidate,old.deadline_at,old.created_at)
   or old.status in ('completed','failed','cancelled') or old.request is not null and new.request is distinct from old.request or old.provider_session_id is not null and new.provider_session_id is distinct from old.provider_session_id or new.candidate_version<old.candidate_version then raise exception 'Original managed repair evidence and limits are immutable';end if;
  new.updated_at=clock_timestamp();
 elsif tg_table_name='research_paper_agent_actions' then
  if old.status='completed' or (new.id,new.call_id,new.workflow_id,new.study_id,new.owner_id,new.position,new.repair_round,new.turn_id,new.provider_call_id,new.name,new.arguments,new.created_at) is distinct from (old.id,old.call_id,old.workflow_id,old.study_id,old.owner_id,old.position,old.repair_round,old.turn_id,old.provider_call_id,old.name,old.arguments,old.created_at) then raise exception 'Original managed action and result are immutable';end if;
 end if;
 return new;
end$$;
drop trigger if exists paper_agent_provider_immutable on public.research_paper_quality_calls;
create trigger paper_agent_provider_immutable before update on public.research_paper_quality_calls for each row execute function public.research_paper_agent_history_guard();
drop trigger if exists paper_agent_history on public.research_paper_agent_sessions;
create trigger paper_agent_history before update or delete on public.research_paper_agent_sessions for each row execute function public.research_paper_agent_history_guard();
drop trigger if exists paper_agent_history on public.research_paper_agent_actions;
create trigger paper_agent_history before update or delete on public.research_paper_agent_actions for each row execute function public.research_paper_agent_history_guard();

-- The live beta does not enforce the SDK's spend_control field or expose a
-- per-session inference-count bound. Never silently relax a finite policy.
create or replace function public.research_paper_agent_limits_allow(study uuid) returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.autonomy_budget_categories where category='research_assessment' and max_spend_cents=-1 and max_model_calls=-1)
 and not exists(select 1 from public.research_autonomy_workflows where study_id=study and max_spend_cents is not null)
$$;
create or replace function public.research_paper_agent_capabilities() returns jsonb language sql stable set search_path='' as $$
 select '{"runtime":"managed-agents-v1","native_records":true,"finite_provider_limits":false}'::jsonb
$$;

-- Freeze the prior qualified implementations for historical call reconciliation.
do $$declare body text;begin
 if to_regprocedure('public.research_paper_quality_control_responses_v3(text,uuid,uuid,jsonb)') is null then
  select prosrc into strict body from pg_proc where oid='public.research_paper_quality_control(text,uuid,uuid,jsonb)'::regprocedure;
  execute 'create function public.research_paper_quality_control_responses_v3(p_operation text,p_actor uuid,p_workflow uuid,p_payload jsonb default ''{}'') returns jsonb language plpgsql security definer set search_path='''' as '||quote_literal(body);
 end if;
 if to_regprocedure('public.research_quality_result_responses_v3(uuid)') is null then
  select prosrc into strict body from pg_proc where oid='public.research_quality_result(uuid)'::regprocedure;
  execute 'create function public.research_quality_result_responses_v3(workflow uuid) returns jsonb language sql stable set search_path='''' as '||quote_literal(body);
 end if;
 if to_regprocedure('public.research_quality_review_context_responses_v3(public.research_paper_quality_workflows)') is null then
  select prosrc into strict body from pg_proc where oid='public.research_quality_review_context(public.research_paper_quality_workflows)'::regprocedure;
  execute 'create function public.research_quality_review_context_responses_v3(w public.research_paper_quality_workflows) returns jsonb language sql stable set search_path='''' as '||quote_literal(body);
 end if;
end$$;
create or replace function public.research_quality_review_context(w public.research_paper_quality_workflows) returns jsonb language sql stable set search_path='' as $$
 select public.research_quality_review_context_responses_v3(w) || case when r.provider_type='managed_agent' then jsonb_build_object('previous_candidate',s.initial_candidate) else '{}'::jsonb end
 from (select 1) anchor left join lateral(select * from public.research_paper_quality_calls where workflow_id=w.id and kind='repair' and status='completed' order by position desc limit 1) r on true
 left join public.research_paper_agent_sessions s on s.call_id=r.id
$$;
create or replace function public.research_quality_result(workflow uuid) returns jsonb language sql stable set search_path='' as $$
 select public.research_quality_result_responses_v3(workflow)||jsonb_build_object('agent',(select to_jsonb(s) from public.research_paper_agent_sessions s join public.research_paper_quality_workflows w on w.current_call_id=s.call_id where w.id=workflow))
$$;
create or replace function public.research_paper_quality_control(p_operation text,p_actor uuid,p_workflow uuid,p_payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
#variable_conflict use_variable
declare w public.research_paper_quality_workflows;c public.research_paper_quality_calls;hash text;cost integer;begin
 if p_operation<>'admit' or p_payload->>'repair_runtime' is distinct from 'managed-agents-v1' then
  if p_operation not in ('admit','context') and exists(select 1 from public.research_paper_quality_workflows qw join public.research_paper_quality_calls qc on qc.id=qw.current_call_id where qw.id=p_workflow and qc.provider_type='managed_agent' and qw.status in ('running','uncertain')) then raise exception 'Managed repairs require their original native runtime control';end if;
  return public.research_paper_quality_control_responses_v3(p_operation,p_actor,p_workflow,p_payload);
 end if;
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into w from public.research_paper_quality_workflows where id=p_workflow for update;
 if p_actor is null or w.id is null or w.owner_id<>p_actor or public.research_assessment_deleted(w.study_id) or not exists(select 1 from public.research_study_owners where study_id=w.study_id and owner_id=p_actor) or not exists(select 1 from auth.users u join auth.identities a on a.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and a.provider='google') then raise exception 'Verified active Google assessment owner required';end if;
 if w.status<>'repair_pending' then return public.research_quality_result(w.id);end if;
 if w.round>=3 or w.deadline_at<=clock_timestamp() then raise exception 'The original assessment deadline or repair bound has expired';end if;
 if not public.research_paper_agent_limits_allow(w.study_id) then raise exception 'Managed agents require provider limits for finite assessment budgets';end if;
 if p_payload->>'review_context_version' is distinct from 'paper-quality-context-v1' then raise exception 'Retained cumulative review context required';end if;
 hash=encode(sha256(convert_to(public.research_quality_canonical(public.research_quality_source(w)),'UTF8')),'hex');
 if p_payload->>'source_sha256' is distinct from hash then raise exception 'Repair only the exact retained draft';end if;
 cost=case when w.step=4 then 200 else 100 end;perform public.research_assert_quality_budget(w.study_id,cost,1);
 insert into public.research_paper_quality_calls(workflow_id,study_id,owner_id,position,kind,source_sha256,reserved_cents,policy_snapshot,deadline_at,provider_type)
 values(w.id,w.study_id,w.owner_id,2*(w.round+1),'repair',hash,cost,public.autonomy_assessment_budget_terms()||'{"quality_context":true,"repair_runtime":"managed-agents-v1","model_calls_semantics":"session_admission_not_inference_count"}'::jsonb,w.deadline_at,'managed_agent') returning * into c;
 insert into public.research_paper_agent_sessions(call_id,workflow_id,study_id,owner_id,submit_token,initial_candidate,candidate,deadline_at)
 values(c.id,w.id,w.study_id,w.owner_id,c.submit_token,w.candidate,w.candidate,w.deadline_at);
 update public.research_paper_quality_workflows set current_call_id=c.id,status='running',phase='repairing' where id=w.id;
 return public.research_quality_result(w.id)||'{"admitted":true}'::jsonb;
end$$;

create or replace function public.research_paper_agent_control(p_operation text,p_actor uuid,p_call uuid,p_payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
#variable_conflict use_variable
declare w public.research_paper_quality_workflows;c public.research_paper_quality_calls;s public.research_paper_agent_sessions;a public.research_paper_agent_actions;
 request jsonb;session jsonb;turn jsonb;action jsonb;result jsonb;checks jsonb;candidate jsonb;configuration jsonb;content jsonb;hash text;prompt uuid;item_key text;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into c from public.research_paper_quality_calls where id=p_call for update;
 select * into w from public.research_paper_quality_workflows where id=c.workflow_id for update;
 select * into s from public.research_paper_agent_sessions where call_id=c.id for update;
 if p_actor is null or c.id is null or s.call_id is null or c.provider_type<>'managed_agent' or c.kind<>'repair' or c.owner_id<>p_actor or w.owner_id<>p_actor or s.owner_id<>p_actor or public.research_assessment_deleted(w.study_id) or not exists(select 1 from public.research_study_owners where study_id=w.study_id and owner_id=p_actor) or not exists(select 1 from auth.users u join auth.identities i on i.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and i.provider='google') then raise exception 'Verified active managed repair owner required';end if;
 if p_operation='limits' then return to_jsonb(public.research_paper_agent_limits_allow(w.study_id));end if;
 if jsonb_typeof(p_payload) is distinct from 'object' or octet_length(p_payload::text)>4000000 then raise exception 'Bounded managed repair evidence required';end if;
 if s.status in ('completed','failed','cancelled') then return public.research_quality_result(w.id);end if;
 if w.current_call_id<>c.id or w.status not in ('running','uncertain') then raise exception 'The original current managed repair is required';end if;
 if p_operation='request' then
  request=p_payload->'request';
  if s.request is not null then if s.request is distinct from request then raise exception 'Original managed request is immutable';end if;return public.research_quality_result(w.id);end if;
  if s.status<>'preparing' or s.deadline_at<=clock_timestamp() or not public.research_paper_agent_limits_allow(w.study_id) then raise exception 'Managed repair requires current original unlimited terms and deadline';end if;
  if request->'agent'->>'model' is distinct from 'gpt-5.4' or request->'agent'->'reasoning' is distinct from '{"effort":"medium"}'::jsonb or request->'agent'->>'service_tier' is distinct from 'default' or request->'agent'->'compaction' is distinct from '{"async":false}'::jsonb or request->'agent'->'multi_agent' is distinct from '{"enabled":false}'::jsonb or request->'environment' is distinct from '{"type":"none"}'::jsonb or request->'metadata' is distinct from jsonb_build_object('runtime','managed-agents-v1','call_id',c.id,'submit_token',c.submit_token)
   or request-array['agent','environment','metadata','input']<>'{}'::jsonb or (request->'agent')-array['model','reasoning','service_tier','compaction','multi_agent','instructions','tools']<>'{}'::jsonb or jsonb_typeof(request->'agent'->'instructions') is distinct from 'string' or length(request->'agent'->>'instructions') not between 1 and 16000 or jsonb_typeof(request->'input') is distinct from 'string'
   or (request->>'input')::jsonb->>'source_sha256' is distinct from c.source_sha256 or ((request->>'input')::jsonb->>'deadline_at')::timestamptz is distinct from s.deadline_at or (request->>'input')::jsonb->'max_actions' is distinct from '24'::jsonb
   or jsonb_typeof(request->'agent'->'tools') is distinct from 'array' or jsonb_array_length(request->'agent'->'tools')<>4 or (select array_agg(t->>'name' order by t->>'name') from jsonb_array_elements(request->'agent'->'tools') t) is distinct from array['apply_patch','read_evidence','record_platform_issue','run_validator']::text[] or exists(select 1 from jsonb_array_elements(request->'agent'->'tools') t where t->>'type' is distinct from 'function') then raise exception 'A bounded environment-free source-bound managed request is required';end if;
  update public.research_paper_agent_sessions set request=request,status='submitting' where call_id=c.id;
  update public.research_paper_quality_calls set request=request,status='submitting' where id=c.id;
  configuration=jsonb_build_object('runtime','managed-agents-v1','model',request->'agent'->'model','reasoning',request->'agent'->'reasoning','agent',(request->'agent')-'instructions','environment',request->'environment','max_actions',24);
  content=jsonb_build_object('instructions',request->'agent'->'instructions','input_template',jsonb_build_object('task','Repair the private stage draft with retained evidence and independent approval.','step','{{step}}','source_sha256','{{source_sha256}}','deadline_at','{{original_deadline}}'),'request_configuration',configuration);
  hash=encode(sha256(convert_to(content::text,'UTF8')),'hex');
  insert into public.research_paper_prompt_versions(version,instructions,input_template,request_configuration,content_sha256,created_at) values('paper-assessment-'||hash,content->>'instructions',content->'input_template',configuration,hash,c.created_at) on conflict(content_sha256) do nothing;
  select id into strict prompt from public.research_paper_prompt_versions where content_sha256=hash;
  insert into public.research_paper_agent_prompt_uses(call_id,study_id,prompt_version_id,request_sha256) values(c.id,w.study_id,prompt,encode(sha256(convert_to(request::text,'UTF8')),'hex'));
  return public.research_quality_result(w.id);
 end if;
 if p_operation='uncertain' then
  if s.provider_session_id is not null then return public.research_quality_result(w.id);end if;
  if s.status='uncertain' then return public.research_quality_result(w.id);end if;
  update public.research_paper_agent_sessions set status='uncertain' where call_id=c.id;
  update public.research_paper_quality_calls set status='uncertain' where id=c.id;
  update public.research_paper_quality_workflows set status='uncertain',phase='uncertain',reason=left(p_payload->>'reason',2000) where id=w.id;
  return public.research_quality_result(w.id);
 end if;
 session=p_payload->'session';turn=p_payload->'turn';
 if session is not null then
  if coalesce(session->>'id','') !~ '^sess_[A-Za-z0-9_-]{1,200}$' or session->'metadata' is distinct from jsonb_build_object('runtime','managed-agents-v1','call_id',c.id,'submit_token',c.submit_token) or s.provider_session_id is not null and session->>'id' is distinct from s.provider_session_id or session->'agent'->>'model' is distinct from 'gpt-5.4' or session->'agent'->'reasoning'->>'effort' is distinct from 'medium' or session->'environment'->>'type' is distinct from 'none' or coalesce(session->'agent'->'multi_agent'->'enabled','false'::jsonb) is distinct from 'false'::jsonb then raise exception 'Original managed session identity and configuration required';end if;
 end if;
 if turn is not null and turn<>'null'::jsonb and (turn->>'session_id' is distinct from s.provider_session_id or s.turn is not null and s.turn<>'null'::jsonb and turn->>'id' is distinct from s.turn->>'id' or turn->'subagent_id' is distinct from 'null'::jsonb) then raise exception 'Original root turn identity required';end if;
 if p_operation='submitted' then
  if s.request is null or session is null then raise exception 'Original submitting request required';end if;
  if s.provider_session_id is not null then return public.research_quality_result(w.id);end if;
  update public.research_paper_agent_sessions set provider_session_id=session->>'id',session=session,status='processing' where call_id=c.id;
  update public.research_paper_quality_calls set status='processing' where id=c.id;
  update public.research_paper_quality_workflows set status='running',phase='repairing',reason=null where id=w.id;
 elsif p_operation='observed' then
  if session is null or s.provider_session_id is null then raise exception 'Original acknowledged session required';end if;
  update public.research_paper_agent_sessions set session=session,turn=case when turn is null or turn='null'::jsonb then s.turn else turn end where call_id=c.id;
 elsif p_operation='cancel_requested' then
  if s.provider_session_id is null then raise exception 'Reconcile the original managed session before cancellation';end if;
  update public.research_paper_agent_sessions set cancel_requested_at=coalesce(cancel_requested_at,clock_timestamp()) where call_id=c.id;
  update public.research_paper_quality_workflows set reason=left(p_payload->>'reason',2000) where id=w.id;
 elsif p_operation='action_claim' then
  if s.provider_session_id is null or s.status<>'processing' or jsonb_typeof(s.session->'required_actions') is distinct from 'array' then raise exception 'An acknowledged session with pending actions is required';end if;
  if s.cancel_requested_at is not null or s.deadline_at<=clock_timestamp() or not public.research_paper_agent_limits_allow(w.study_id) then raise exception 'The managed repair deadline or current limits stop further actions';end if;
  action=p_payload->'action';
  if action->>'type' is distinct from 'function_call' or not coalesce(s.session->'required_actions' @> jsonb_build_array(action),false) or coalesce(action->>'name','') not in ('read_evidence','apply_patch','run_validator','record_platform_issue') or length(action->>'turn_id') not between 1 and 200 or length(action->>'call_id') not between 1 and 200 or octet_length((action->'arguments')::text)>1100000 then raise exception 'Only an exact pending scoped function call may run';end if;
  select * into a from public.research_paper_agent_actions where call_id=c.id and turn_id=action->>'turn_id' and provider_call_id=action->>'call_id' for update;
  if a.id is not null then
   if a.name is distinct from action->>'name' or a.arguments is distinct from action->'arguments' then raise exception 'Original function identity conflicts';end if;
   if a.status='completed' or a.lease_until>clock_timestamp() then return to_jsonb(a)||jsonb_build_object('call_id',a.provider_call_id,'admitted',false,'workflow',public.research_quality_result(w.id));end if;
   update public.research_paper_agent_actions set lease_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '90 seconds',candidate_version=s.candidate_version where id=a.id returning * into a;
  else
   if (select count(*) from public.research_paper_agent_actions where call_id=c.id)>=24 then raise exception 'Managed repair action limit reached';end if;
   insert into public.research_paper_agent_actions(call_id,workflow_id,study_id,owner_id,position,repair_round,turn_id,provider_call_id,name,arguments,lease_until,candidate_version)
   values(c.id,w.id,w.study_id,w.owner_id,(select count(*)+1 from public.research_paper_agent_actions where call_id=c.id),w.round+1,action->>'turn_id',action->>'call_id',action->>'name',action->'arguments',clock_timestamp()+interval '90 seconds',s.candidate_version) returning * into a;
  end if;
  return to_jsonb(a)||jsonb_build_object('call_id',a.provider_call_id,'admitted',true,'workflow',public.research_quality_result(w.id));
 elsif p_operation='action_result' then
  select * into a from public.research_paper_agent_actions where id=(p_payload->>'action_id')::uuid and call_id=c.id for update;
  if a.id is null or a.lease_token::text is distinct from p_payload->>'lease_token' then raise exception 'The claimed action lease is required';end if;
  result=p_payload->'result';checks=p_payload->'checks';candidate=p_payload->'candidate';
  if a.status='completed' then if a.result is distinct from result then raise exception 'Original action result conflicts';end if;return public.research_quality_result(w.id);end if;
  if s.cancel_requested_at is not null or s.deadline_at<=clock_timestamp() or not public.research_paper_agent_limits_allow(w.study_id) then raise exception 'The current stop or limits prevent further draft actions';end if;
  if a.candidate_version<>s.candidate_version or a.candidate_version::text is distinct from p_payload->>'candidate_version' or a.lease_until<=clock_timestamp() then raise exception 'The current candidate version and action lease are required';end if;
  if jsonb_typeof(result->'success') is distinct from 'boolean' or result->'success'='true'::jsonb and jsonb_typeof(result->'output') is distinct from 'string' or result->'success'='false'::jsonb and (jsonb_typeof(result->'error') is distinct from 'string' or length(result->>'error')>2000) then raise exception 'Retain a bounded exact tool result';end if;
  if candidate is not null then
   if a.name<>'apply_patch' or result->'success' is distinct from 'true'::jsonb or not public.research_valid_quality_candidate(w,candidate) or checks->'passed' is distinct from 'true'::jsonb then raise exception 'A source-valid candidate from the scoped patch tool is required';end if;
   hash=encode(sha256(convert_to(public.research_quality_canonical(w.source_json||jsonb_build_object('candidate',candidate)),'UTF8')),'hex');
   if checks->>'source_sha256' is distinct from hash then raise exception 'Patch checks must match the saved candidate';end if;
   update public.research_paper_agent_sessions set candidate=candidate,candidate_version=candidate_version+1 where call_id=c.id;
  elsif checks is not null then
   hash=encode(sha256(convert_to(public.research_quality_canonical(w.source_json||jsonb_build_object('candidate',s.candidate)),'UTF8')),'hex');
   if a.name<>'run_validator' or checks->>'source_sha256' is distinct from hash then raise exception 'Validator evidence must match this draft';end if;
  end if;
  update public.research_paper_agent_actions set result=result,checks=checks,status='completed',completed_at=clock_timestamp() where id=a.id;
  insert into public.research_paper_agent_events(call_id,workflow_id,study_id,kind,snapshot) values(c.id,w.id,w.study_id,'action_result',jsonb_build_object('action_id',a.id,'result',result,'candidate',candidate,'checks',checks));
  if p_payload ? 'issue' then
   if a.name<>'record_platform_issue' or p_payload->'issue' is distinct from (case when jsonb_typeof(a.arguments)='string' then (a.arguments#>>'{}')::jsonb else a.arguments end) then raise exception 'Retain the exact recorded platform diagnosis';end if;
   insert into public.research_paper_agent_events(call_id,workflow_id,study_id,kind,snapshot) values(c.id,w.id,w.study_id,'platform_issue',p_payload->'issue');
  end if;
  return public.research_quality_result(w.id);
 elsif p_operation='action_ack' then
  return to_jsonb(s.cancel_requested_at is null and s.deadline_at>clock_timestamp() and public.research_paper_agent_limits_allow(w.study_id) and exists(select 1 from public.research_paper_agent_actions saved where saved.call_id=c.id and saved.turn_id=p_payload->>'turn_id' and saved.provider_call_id=p_payload->>'call_id' and saved.status='completed'));
 elsif p_operation='history_item' then
  content=p_payload->'item';
  if jsonb_typeof(content) is distinct from 'object' or octet_length(content::text)>2000000 or s.provider_session_id is null or coalesce(s.session->>'status','')<>'failed' and coalesce(s.turn->>'status','') not in ('completed','failed','cancelled') then raise exception 'A bounded original terminal-session item is required';end if;
  hash=encode(sha256(convert_to(public.research_quality_canonical(content),'UTF8')),'hex');item_key=coalesce(content->>'id','sha256:'||hash);
  if length(item_key) not between 1 and 240 then raise exception 'A bounded original item identity is required';end if;
  insert into public.research_paper_agent_items(call_id,item_key,content_sha256,data) values(c.id,item_key,hash,content) on conflict on constraint research_paper_agent_items_pkey do nothing;
  if not exists(select 1 from public.research_paper_agent_items original where original.call_id=c.id and original.item_key=item_key and original.data=content) then raise exception 'The original provider item cannot change';end if;
  return jsonb_build_object('item_key',item_key,'sha256',hash,'type',content->'type','retained_in','research_paper_agent_items');
 elsif p_operation='controller_checks' then
  checks=p_payload->'checks';hash=encode(sha256(convert_to(public.research_quality_canonical(w.source_json||jsonb_build_object('candidate',s.candidate)),'UTF8')),'hex');
  if checks->'passed' is distinct from 'true'::jsonb or checks->>'source_sha256' is distinct from hash or not public.research_valid_quality_candidate(w,s.candidate) then raise exception 'Final controller validation must match the retained draft';end if;
 elsif p_operation in ('completed','failed','cancelled') then
  if p_operation='completed' then
   checks=p_payload->'checks';
   hash=encode(sha256(convert_to(public.research_quality_canonical(w.source_json||jsonb_build_object('candidate',s.candidate)),'UTF8')),'hex');
   if session is null or session->>'status' is distinct from 'idle' or turn->>'status' is distinct from 'completed' or s.cancel_requested_at is not null or checks->'passed' is distinct from 'true'::jsonb or checks->>'source_sha256' is distinct from hash or not public.research_valid_quality_candidate(w,s.candidate)
    or not exists(select 1 from public.research_paper_agent_events checked where checked.call_id=c.id and checked.kind='controller_checks' and checked.snapshot->'checks'->'passed'='true'::jsonb and checked.snapshot->'checks'->>'source_sha256'=hash) or jsonb_typeof(p_payload->'items') is distinct from 'array'
    or jsonb_array_length(p_payload->'items')=0 or jsonb_array_length(p_payload->'items')<>(select count(*) from public.research_paper_agent_items where call_id=c.id)
    or exists(select 1 from jsonb_array_elements(p_payload->'items') manifest where manifest->>'retained_in' is distinct from 'research_paper_agent_items' or not exists(select 1 from public.research_paper_agent_items original where original.call_id=c.id and original.item_key=manifest->>'item_key' and original.content_sha256=manifest->>'sha256')) then raise exception 'A completed original turn and final source-bound validation are required';end if;
   update public.research_paper_agent_sessions set status='completed',session=session,turn=turn where call_id=c.id;
   update public.research_paper_quality_calls set status='completed',response=jsonb_build_object('runtime','managed-agents-v1','session',session,'turn',turn,'items',p_payload->'items') where id=c.id;
   update public.research_paper_quality_workflows set candidate=s.candidate,checks=checks,round=round+1,status='review_pending',phase='reviewing',reason=null where id=w.id;
  else
   if p_operation='failed' and s.provider_session_id is not null and (session is null or not (session->>'status'='failed' or session->>'status'='idle' and turn->>'status' in ('cancelled','completed','failed'))) then raise exception 'Retain an active provider session until terminal evidence or confirmed cancellation';end if;
   if p_operation='cancelled' and (s.provider_session_id is null or session is null or session->>'status' is distinct from 'idle' or coalesce(turn->>'status','') not in ('cancelled','completed','failed')) then raise exception 'Confirmed provider terminal evidence required for cancellation';end if;
   if s.provider_session_id is null and s.status='uncertain' then raise exception 'Reconcile the original unknown managed submission first';end if;
   update public.research_paper_agent_sessions set status=case when p_operation='cancelled' then 'cancelled' else 'failed' end,session=coalesce(session,s.session),turn=coalesce(turn,s.turn) where call_id=c.id;
   update public.research_paper_quality_calls set status=case when p_operation='cancelled' then 'cancelled' else 'failed' end,response=p_payload-array['reason'] where id=c.id;
   update public.research_paper_quality_workflows set status=case when p_operation='cancelled' then 'cancelled' else 'needs_attention' end,phase=case when p_operation='cancelled' then 'cancelled' else 'needs_attention' end,reason=left(p_payload->>'reason',2000) where id=w.id;
  end if;
 else raise exception 'Unknown managed repair operation';
 end if;
 insert into public.research_paper_agent_events(call_id,workflow_id,study_id,kind,snapshot) values(c.id,w.id,w.study_id,p_operation,p_payload);
 return public.research_quality_result(w.id);
end$$;

do $$declare proc regprocedure;begin
 for proc in select oid::regprocedure from pg_proc where pronamespace='public'::regnamespace and (proname like 'research_paper_agent_%' or proname in ('research_paper_quality_control','research_paper_quality_control_responses_v3','research_quality_result_responses_v3','research_quality_review_context_responses_v3','research_quality_result','research_quality_review_context')) loop
  execute format('revoke all on function %s from public,anon,authenticated,service_role',proc);
 end loop;
end$$;
grant execute on function public.research_paper_quality_control(text,uuid,uuid,jsonb),public.research_paper_agent_control(text,uuid,uuid,jsonb),public.research_paper_agent_capabilities() to service_role;
notify pgrst,'reload schema';
commit;
