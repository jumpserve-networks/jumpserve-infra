begin;
-- Individual, explicitly requested Step 3 calls. Historical experiment-wide
-- packages, requests, responses, confirmations, reservations and events remain
-- unchanged. Admission and all original limits are enforced atomically.
create table if not exists public.research_step_commands (
 id uuid primary key default gen_random_uuid(),study_id uuid not null references public.research_experiment_plans(study_id),owner_id uuid not null,
 experiment_index integer not null check(experiment_index between 1 and 8),action_ref text not null check(length(action_ref) between 3 and 20),command_layout text not null default 'action-v1' check(command_layout='action-v1'),target text not null check(target='ubuntu-debian'),
 plan_revision integer not null,link_review_id uuid references public.research_experiment_plan_link_reviews(id),source_plan jsonb not null,confirmed_breakdown jsonb not null,
 status text not null check(status in ('submitting','processing','uncertain','ready','failed','cancelled')),
 submit_token uuid not null,provider_response_id text unique,request jsonb not null,response jsonb,command_set jsonb,reason text,generated_at timestamptz,
 model_calls integer not null check(model_calls=1),reserved_cents integer not null check(reserved_cents=200),policy_snapshot jsonb not null,deadline_at timestamptz not null,
 created_at timestamptz not null default clock_timestamp(),updated_at timestamptz not null default clock_timestamp(),revision integer not null default 1,
 unique(study_id,experiment_index,action_ref,target),check(status<>'ready' or command_set is not null and generated_at is not null),
 check(provider_response_id is null or provider_response_id ~ '^resp_[A-Za-z0-9_-]{1,200}$')
);
create table if not exists public.research_step_command_events (
 id bigint generated always as identity primary key,command_id uuid not null references public.research_step_commands(id),study_id uuid not null,
 revision integer not null,snapshot jsonb not null,created_at timestamptz not null default clock_timestamp(),unique(command_id,revision)
);
create table if not exists public.research_step_command_prompt_uses (
 command_id uuid primary key references public.research_step_commands(id),study_id uuid not null,
 prompt_version_id uuid not null references public.research_paper_prompt_versions(id),request_sha256 text not null,recorded_at timestamptz not null default clock_timestamp()
);
alter table public.research_step_commands enable row level security;
alter table public.research_step_command_events enable row level security;
alter table public.research_step_command_prompt_uses enable row level security;
revoke all on public.research_step_commands,public.research_step_command_events,public.research_step_command_prompt_uses from public,anon,authenticated,service_role;
grant select on public.research_step_commands,public.research_step_command_events,public.research_step_command_prompt_uses to service_role;
drop trigger if exists command_assessment_active on public.research_step_commands;
create trigger command_assessment_active before insert or update on public.research_step_commands for each row execute function public.research_require_active_assessment();
drop trigger if exists command_event_immutable on public.research_step_command_events;
create trigger command_event_immutable before update or delete on public.research_step_command_events for each row execute function public.research_immutable();
drop trigger if exists command_prompt_immutable on public.research_step_command_prompt_uses;
create trigger command_prompt_immutable before update or delete on public.research_step_command_prompt_uses for each row execute function public.research_immutable();
create or replace function public.research_step_command_history() returns trigger language plpgsql set search_path='' as $$begin
 if tg_op='DELETE' then raise exception 'Retain terminal command history';end if;
 if tg_op='UPDATE' then
  if (new.id,new.study_id,new.owner_id,new.experiment_index,new.action_ref,new.command_layout,new.target,new.plan_revision,new.link_review_id,new.source_plan,new.confirmed_breakdown,new.submit_token,new.request,new.model_calls,new.reserved_cents,new.policy_snapshot,new.deadline_at,new.created_at)
   is distinct from (old.id,old.study_id,old.owner_id,old.experiment_index,old.action_ref,old.command_layout,old.target,old.plan_revision,old.link_review_id,old.source_plan,old.confirmed_breakdown,old.submit_token,old.request,old.model_calls,old.reserved_cents,old.policy_snapshot,old.deadline_at,old.created_at)
   or old.status in ('ready','failed','cancelled') or old.provider_response_id is not null and new.provider_response_id is distinct from old.provider_response_id
  then raise exception 'Original command scope, request, provider identity, terminal result and limits are immutable';end if;
  new.revision=old.revision+1;new.updated_at=clock_timestamp();
 end if;return new;
end$$;
drop trigger if exists command_history on public.research_step_commands;
create trigger command_history before insert or update or delete on public.research_step_commands for each row execute function public.research_step_command_history();
create or replace function public.research_step_command_audit() returns trigger language plpgsql set search_path='' as $$begin
 insert into public.research_step_command_events(command_id,study_id,revision,snapshot) values(new.id,new.study_id,new.revision,to_jsonb(new));return new;
end$$;
drop trigger if exists command_audit on public.research_step_commands;
create trigger command_audit after insert or update on public.research_step_commands for each row execute function public.research_step_command_audit();
create or replace function public.research_pending_step_command_delete_guard() returns trigger language plpgsql set search_path='' as $$begin
 if old.deleted_at is null and new.deleted_at is not null and exists(select 1 from public.research_step_commands c where c.study_id=old.id and c.status in ('submitting','processing','uncertain')) then raise exception 'Cancel or reconcile the original terminal command generation before deleting this assessment';end if;return new;
end$$;
drop trigger if exists pending_step_command_delete on public.research_studies;
create trigger pending_step_command_delete before update of deleted_at on public.research_studies for each row execute function public.research_pending_step_command_delete_guard();


-- HELPERS
create or replace function public.research_step_commands_input(study uuid,n integer,ref text,p jsonb,b jsonb) returns jsonb language sql immutable set search_path='' as $$
 with refs as (select value,ordinality from jsonb_array_elements_text(public.research_terminal_action_refs(p,n)) with ordinality),
 selected as (select ordinality from refs where value=ref),
 action as (select case when (p->'experiments'->(n-1)) ? 'stages' then p->'experiments'->(n-1)->'stages'->((split_part(ref,'.',2))::integer-1)->'steps'->((split_part(ref,'.',3))::integer-1) else p->'experiments'->(n-1)->'steps'->((split_part(ref,'.',2))::integer-1) end as item)
 select jsonb_build_object('phase','paper-step-commands-v1','target','ubuntu-debian','command_layout','action-v1','study_id',study,'experiment_index',n,'action_ref',ref,'confirmed',public.research_experiment_plan_input(b),'experiment',p->'experiments'->(n-1),'selected_action',(select item from action),'earlier_action_refs',coalesce((select jsonb_agg(value order by ordinality) from refs where ordinality<(select ordinality from selected)),'[]'::jsonb),'artifact_contract','step-manifest-v1')
$$;

create or replace function public.research_valid_step_commands(v jsonb,p jsonb,n integer,ref text,b jsonb) returns boolean language plpgsql immutable set search_path='' as $$
declare refs jsonb;prior jsonb;expanded jsonb;context_actions jsonb;blocked jsonb;position bigint;begin
 if jsonb_typeof(v) is distinct from 'object' or octet_length(v::text)>100000 or jsonb_typeof(v->'actions') is distinct from 'object' or
  not (v->'actions') ? ref or (v->'actions')-ref<>'{}'::jsonb then return false;end if;
 refs=public.research_terminal_action_refs(p,n);
 select ordinality into position from jsonb_array_elements_text(refs) with ordinality r(value,ordinality) where value=ref;
 if position is null then return false;end if;
 select coalesce(jsonb_agg(value order by ordinality),'[]'::jsonb) into prior from jsonb_array_elements_text(refs) with ordinality r(value,ordinality) where ordinality<position;
 blocked=case when public.research_terminal_blocked_refs(p,n,b) ? ref then jsonb_build_array(ref) else '[]'::jsonb end;
 if blocked ? ref and v->'cleanup'->>'kind'='terminal' then return false;end if;
 -- Context-only placeholders seed the existing ordered-prerequisite validator.
 -- They are never model output, saved commands, evidence or displayed actions.
 select coalesce(jsonb_object_agg(value,jsonb_build_object('kind','manual','commands',null,'prerequisites','[]'::jsonb,'verification','Validation context only.','notes','Not generated or stored.','needs_sudo',false)),'{}'::jsonb) into context_actions from jsonb_array_elements_text(prior);
 expanded=jsonb_set(v,'{actions}',context_actions||(v->'actions'));
 return public.research_valid_standalone_terminal_commands(expanded,prior||jsonb_build_array(ref),blocked);
end$$;

create or replace function public.research_step_commands_control(p_operation text,p_actor uuid,p_study uuid,p_index integer,p_ref text,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare p public.research_experiment_plans;c public.research_step_commands;r public.research_experiment_plan_link_reviews;w public.research_autonomy_workflows;
 source_plan jsonb;request jsonb;configuration jsonb;template jsonb;content jsonb;hash text;prompt uuid;output text;spent bigint=0;calls bigint=0;reserved bigint=0;prior_calls bigint=0;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or public.research_assessment_deleted(p_study) or not exists(select 1 from auth.users u join auth.identities a on a.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and a.provider='google') then raise exception 'Verified active Google owner required';end if;
 select * into p from public.research_experiment_plans where study_id=p_study for update;
 if p.study_id is null or p.owner_id<>p_actor or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private assessment not found';end if;
 if p_index is null or p_index not between 1 and 8 or p_ref is null or length(p_ref) not between 3 and 20 or jsonb_typeof(p_payload) is distinct from 'object' or octet_length(p_payload::text)>1500000 then raise exception 'Bounded experiment command request required';end if;
 select * into c from public.research_step_commands where study_id=p_study and experiment_index=p_index and action_ref=p_ref and target='ubuntu-debian' for update;
 if p_operation='generate' then
  if c.id is not null then return to_jsonb(c)||'{"admitted":false}'::jsonb;end if;
  if p.status='ready' then source_plan=p.plan;
  elsif p.status='failed' then select * into r from public.research_experiment_plan_link_reviews where study_id=p_study and owner_id=p_actor and base_revision=p.revision and provider_response_id=p.provider_response_id;source_plan=r.plan;
  end if;
  if source_plan is null or not public.research_valid_experiment_plan(source_plan,p.confirmed_breakdown) or p_index>jsonb_array_length(source_plan->'experiments') or not public.research_terminal_action_refs(source_plan,p_index) ? p_ref then raise exception 'A saved ready numbered step is required';end if;
  if exists(select 1 from public.research_terminal_commands where study_id=p_study and experiment_index=p_index and status in ('submitting','processing','uncertain')) then raise exception 'Reconcile or cancel the earlier experiment-wide command request before generating individual steps';end if;
  if p.deadline_at<=clock_timestamp() then raise exception 'The original assessment deadline has expired';end if;
  request=p_payload->'request';
  if p_payload-array['request']<>'{}'::jsonb or jsonb_typeof(request) is distinct from 'object' or request->>'model' is distinct from 'gpt-5.4-2026-03-05' or request->'background' is distinct from 'true'::jsonb or request->'store' is distinct from 'true'::jsonb or request->>'max_output_tokens' is distinct from '16000' or jsonb_typeof(request->'instructions') is distinct from 'string' or length(request->>'instructions') not between 1 and 40000 or jsonb_typeof(request->'input') is distinct from 'string' or octet_length(request::text)>300000 or request-array['model','instructions','input','background','store','reasoning','max_output_tokens','text']<>'{}'::jsonb or request->'text'->'format'->>'name' is distinct from 'paper_step_commands_v1' then raise exception 'A bounded server-side command-generation request is required';end if;
  if (request->>'input')::jsonb is distinct from public.research_step_commands_input(p_study,p_index,p_ref,source_plan,p.confirmed_breakdown) then raise exception 'Generate commands only from the exact saved experiment';end if;
  if octet_length(request->>'input')>100000 or request->'max_output_tokens' is distinct from '16000'::jsonb or request->'reasoning'->>'effort' is distinct from 'medium' or
   request->'text'->'format'->>'type' is distinct from 'json_schema' or request->'text'->'format'->'strict' is distinct from 'true'::jsonb or
   request->'text'->'format'->'schema'->'properties'->'actions'->'required' is distinct from jsonb_build_array(p_ref) or
   jsonb_typeof(request->'text'->'format'->'schema'->'properties'->'actions'->'properties') is distinct from 'object' or
   (request->'text'->'format'->'schema'->'properties'->'actions'->'properties')-p_ref<>'{}'::jsonb or
   not (request->'text'->'format'->'schema'->'properties'->'actions'->'properties') ? p_ref then raise exception 'Request exactly one bounded step output';end if;
  select * into w from public.research_autonomy_workflows where study_id=p_study;
  if found then spent=w.committed_cents;select coalesce(sum(attempts),0) into calls from public.research_autonomy_tasks where study_id=p_study;end if;
  select coalesce(sum(reserved_cents),0),coalesce(sum(model_calls),0) into reserved,prior_calls from (select reserved_cents,model_calls from public.research_terminal_commands where study_id=p_study union all select reserved_cents,model_calls from public.research_step_commands where study_id=p_study) prior;
  select spent+reserved_cents, calls+model_calls into spent,calls from public.research_paper_intakes where study_id=p_study;
  spent=spent+p.reserved_cents+reserved;calls=calls+p.model_calls+prior_calls;
  if w.study_id is not null and w.max_spend_cents is not null and spent+200>w.max_spend_cents then raise exception 'The original assessment spending limit does not admit command generation';end if;
  if not public.autonomy_budget_allows('research_assessment',spent,calls,200,1) then raise exception 'The assessment budget does not admit command generation';end if;
  insert into public.research_step_commands(study_id,owner_id,experiment_index,action_ref,target,plan_revision,link_review_id,source_plan,confirmed_breakdown,status,submit_token,request,model_calls,reserved_cents,policy_snapshot,deadline_at,reason)
   values(p_study,p_actor,p_index,p_ref,'ubuntu-debian',p.revision,r.id,source_plan,p.confirmed_breakdown,'submitting',gen_random_uuid(),request,1,200,public.autonomy_assessment_budget_terms(),p.deadline_at,'Submitting terminal command generation.') returning * into c;
  configuration=request-array['input','instructions'];template='{"phase":"paper-step-commands-v1","command_layout":"action-v1","action_ref":"{{selected_step_number}}","selected_action":"{{selected_saved_action}}","earlier_action_refs":"{{earlier_saved_action_numbers}}","artifact_contract":"step-manifest-v1","target":"ubuntu-debian","study_id":"{{assessment_id}}","experiment_index":"{{experiment_number}}","confirmed":"{{confirmed_paper_sections}}","experiment":"{{saved_experiment_stages_and_actions}}"}'::jsonb;
  content=jsonb_build_object('instructions',request->>'instructions','input_template',template,'request_configuration',configuration);hash=encode(sha256(convert_to(content::text,'UTF8')),'hex');
  insert into public.research_paper_prompt_versions(version,instructions,input_template,request_configuration,content_sha256,created_at) values('paper-assessment-'||hash,request->>'instructions',template,configuration,hash,c.created_at) on conflict(content_sha256) do nothing;
  select id into strict prompt from public.research_paper_prompt_versions where content_sha256=hash;
  insert into public.research_step_command_prompt_uses(command_id,study_id,prompt_version_id,request_sha256) values(c.id,p_study,prompt,encode(sha256(convert_to(request::text,'UTF8')),'hex'));
  insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'generate-step-commands',jsonb_build_object('command_id',c.id,'experiment_index',p_index,'action_ref',p_ref,'model_calls',1,'experiments_started',0));
  return to_jsonb(c)||'{"admitted":true}'::jsonb;
 end if;
 if c.id is null or c.submit_token is distinct from (p_payload->>'token')::uuid then raise exception 'The original command call token is required';end if;
 if p_operation='submitted' then
  if c.provider_response_id is not null then if c.provider_response_id is distinct from p_payload->>'response_id' then raise exception 'Original provider identity cannot change';end if;return to_jsonb(c);end if;
  if c.status not in ('submitting','uncertain') or coalesce(p_payload->>'response_id','') !~ '^resp_[A-Za-z0-9_-]{1,200}$' then raise exception 'Original submitting command call required';end if;
  update public.research_step_commands set status='processing',provider_response_id=p_payload->>'response_id',response=p_payload->'response',reason='Generating terminal commands.' where id=c.id returning * into c;return to_jsonb(c);
 end if;
 if c.status in ('ready','failed','cancelled') then return to_jsonb(c);end if;
 if p_operation='uncertain' then
  if c.provider_response_id is not null then return to_jsonb(c);end if;
  update public.research_step_commands set status='uncertain',reason=left(p_payload->>'reason',2000) where id=c.id returning * into c;return to_jsonb(c);
 end if;
 if p_operation='finish' then
  if c.status<>'processing' or c.provider_response_id is distinct from p_payload->>'response_id' or p_payload->'response'->>'id' is distinct from c.provider_response_id or p_payload->'response'->>'status' is distinct from 'completed' or not public.research_valid_step_commands(p_payload->'command_set',c.source_plan,c.experiment_index,c.action_ref,c.confirmed_breakdown) then raise exception 'Verified original response and a complete step-bound command set are required';end if;
  select string_agg(part.item->>'text','' order by message.position,part.position) into output
   from jsonb_array_elements(p_payload->'response'->'output') with ordinality message(item,position)
   cross join lateral jsonb_array_elements(case when message.item->>'type'='message' then message.item->'content' else '[]'::jsonb end) with ordinality part(item,position)
   where part.item->>'type'='output_text';
  if output::jsonb is distinct from p_payload->'command_set' then raise exception 'Retain the original generated command content';end if;
  update public.research_step_commands set status='ready',command_set=p_payload->'command_set',response=p_payload->'response',generated_at=clock_timestamp(),reason=null where id=c.id returning * into c;return to_jsonb(c);
 end if;
 if p_operation in ('failed','cancel') then
  if p_operation='cancel' and (c.provider_response_id is null or p_payload->'response'->>'id' is distinct from c.provider_response_id or p_payload->'response'->>'status' is distinct from 'cancelled') then raise exception 'Confirmed provider cancellation required';end if;
  if c.status='uncertain' then raise exception 'Reconcile the uncertain original command call first';end if;
  update public.research_step_commands set status=case when p_operation='cancel' then 'cancelled' else 'failed' end,response=coalesce(p_payload->'response',response),reason=left(p_payload->>'reason',2000) where id=c.id returning * into c;return to_jsonb(c);
 end if;raise exception 'Unknown terminal command operation';
end$$;

-- FOOTER
-- Stop new experiment-wide admissions. Existing provider identities, polling,
-- cancellation and immutable history continue through the original implementation.
do $$begin
 if to_regprocedure('public.research_terminal_commands_control_before_individual_steps(text,uuid,uuid,integer,jsonb)') is null then
  alter function public.research_terminal_commands_control(text,uuid,uuid,integer,jsonb) rename to research_terminal_commands_control_before_individual_steps;
 end if;
end$$;
create or replace function public.research_terminal_commands_control(p_operation text,p_actor uuid,p_study uuid,p_index integer,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$begin
 if p_operation='generate' then raise exception 'Generate terminal commands for one numbered step';end if;
 return public.research_terminal_commands_control_before_individual_steps(p_operation,p_actor,p_study,p_index,p_payload);
end$$;
revoke all on function public.research_terminal_commands_control_before_individual_steps(text,uuid,uuid,integer,jsonb) from public,anon,authenticated,service_role;
revoke all on function public.research_step_commands_input(uuid,integer,text,jsonb,jsonb),public.research_valid_step_commands(jsonb,jsonb,integer,text,jsonb),public.research_step_commands_control(text,uuid,uuid,integer,text,jsonb),public.research_step_command_history(),public.research_step_command_audit(),public.research_pending_step_command_delete_guard(),public.research_terminal_commands_control(text,uuid,uuid,integer,jsonb) from public,anon,authenticated;
grant execute on function public.research_step_commands_input(uuid,integer,text,jsonb,jsonb),public.research_valid_step_commands(jsonb,jsonb,integer,text,jsonb),public.research_step_commands_control(text,uuid,uuid,integer,text,jsonb),public.research_terminal_commands_control(text,uuid,uuid,integer,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
