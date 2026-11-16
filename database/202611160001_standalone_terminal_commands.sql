begin;
-- A new layout gets a new bounded call; old packages and original responses remain immutable.
alter table public.research_terminal_commands add column if not exists command_layout text not null default 'shared-setup-v1' check(command_layout in ('shared-setup-v1','per-step-v1'));
do $$declare k record;begin
 for k in select conname from pg_constraint c where c.conrelid='public.research_terminal_commands'::regclass and c.contype='u'
  and array(select a.attname::text from unnest(c.conkey) with ordinality x(attnum,position) join pg_attribute a on a.attrelid=c.conrelid and a.attnum=x.attnum order by x.position)=array['study_id','experiment_index','target']
 loop execute format('alter table public.research_terminal_commands drop constraint %I',k.conname);end loop;
 if not exists(select 1 from pg_constraint where conrelid='public.research_terminal_commands'::regclass and conname='research_terminal_commands_layout_key') then
  alter table public.research_terminal_commands add constraint research_terminal_commands_layout_key unique(study_id,experiment_index,target,command_layout);
 end if;
end$$;
create or replace function public.research_valid_standalone_terminal_commands(v jsonb,refs jsonb,blocked jsonb default '[]') returns boolean language plpgsql immutable set search_path='' as $body$
declare block jsonb;begin
 if not public.research_valid_terminal_commands(v,refs,blocked) then return false;end if;
 if v->'setup'->>'kind' is distinct from 'manual' or v->'setup'->'commands' is distinct from 'null'::jsonb or v->'setup'->'prerequisites' is distinct from '[]'::jsonb or v->'setup'->'needs_sudo' is distinct from 'false'::jsonb then return false;end if;
 for block in select value from jsonb_each(v->'actions') union all select v->'cleanup' loop
  if block->'prerequisites' ? 'setup' then return false;end if;
  if block->>'kind'='terminal' and (block->>'commands') ~ $rx$\m(experiment_helper|jumpserve_helper)\.py\M|\m(python3?|bash|sh)[[:space:]]+["']?\$\{?HELPER\M|(^|[;\n])[[:space:]]*(source|\.)[[:space:]]+["']?\$(\{|[A-Z_])$rx$ then return false;end if;
  if block->>'kind'='terminal' and (block->>'commands') ~ $rx$(os[.]readlink|\mopen)[[:space:]]*[(][[:space:]]*f?["']/proc/[{][^}]+[}]/(exe|cmdline|ns/net)["']$rx$ then return false;end if;
 end loop;return true;
end$body$;
create or replace function public.research_terminal_command_history() returns trigger language plpgsql set search_path='' as $$begin
 if tg_op='DELETE' then raise exception 'Retain terminal command history';end if;
 if tg_op='UPDATE' then
  if (new.id,new.study_id,new.owner_id,new.experiment_index,new.target,new.command_layout,new.plan_revision,new.link_review_id,new.source_plan,new.confirmed_breakdown,new.submit_token,new.request,new.model_calls,new.reserved_cents,new.policy_snapshot,new.deadline_at,new.created_at)
   is distinct from (old.id,old.study_id,old.owner_id,old.experiment_index,old.target,old.command_layout,old.plan_revision,old.link_review_id,old.source_plan,old.confirmed_breakdown,old.submit_token,old.request,old.model_calls,old.reserved_cents,old.policy_snapshot,old.deadline_at,old.created_at)
   or old.status in ('ready','failed','cancelled') or old.provider_response_id is not null and new.provider_response_id is distinct from old.provider_response_id
  then raise exception 'Original command scope, request, provider identity, terminal result and limits are immutable';end if;
  new.revision=old.revision+1;new.updated_at=clock_timestamp();
 end if;return new;
end$$;
create or replace function public.research_terminal_commands_control(p_operation text,p_actor uuid,p_study uuid,p_index integer,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare p public.research_experiment_plans;c public.research_terminal_commands;r public.research_experiment_plan_link_reviews;w public.research_autonomy_workflows;
 source_plan jsonb;request jsonb;configuration jsonb;template jsonb;content jsonb;hash text;prompt uuid;output text;spent bigint=0;calls bigint=0;reserved bigint=0;prior_calls bigint=0;v_layout text=coalesce(p_payload->>'command_layout','shared-setup-v1');begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or public.research_assessment_deleted(p_study) or not exists(select 1 from auth.users u join auth.identities a on a.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and a.provider='google') then raise exception 'Verified active Google owner required';end if;
 select * into p from public.research_experiment_plans where study_id=p_study for update;
 if p.study_id is null or p.owner_id<>p_actor or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private assessment not found';end if;
 if p_index is null or p_index not between 1 and 8 or jsonb_typeof(p_payload) is distinct from 'object' or octet_length(p_payload::text)>1500000 then raise exception 'Bounded experiment command request required';end if;
 if v_layout not in ('shared-setup-v1','per-step-v1') then raise exception 'Unknown terminal command layout';end if;
 select * into c from public.research_terminal_commands where study_id=p_study and experiment_index=p_index and target='ubuntu-debian' and command_layout=v_layout for update;
 if p_operation='generate' then
  if c.id is not null then return to_jsonb(c)||'{"admitted":false}'::jsonb;end if;
  if exists(select 1 from public.research_terminal_commands where study_id=p_study and experiment_index=p_index and target='ubuntu-debian' and command_layout<>v_layout and status in ('submitting','processing','uncertain')) then raise exception 'Reconcile the original command request before preparing a different layout';end if;
  if p.status='ready' then source_plan=p.plan;
  elsif p.status='failed' then select * into r from public.research_experiment_plan_link_reviews where study_id=p_study and owner_id=p_actor and base_revision=p.revision;source_plan=r.plan;
  end if;
  if source_plan is null or not public.research_valid_experiment_plan(source_plan,p.confirmed_breakdown) or p_index>jsonb_array_length(source_plan->'experiments') then raise exception 'A saved ready experiment is required';end if;
  if p.deadline_at<=clock_timestamp() then raise exception 'The original assessment deadline has expired';end if;
  request=p_payload->'request';
  if p_payload-array['request','command_layout']<>'{}'::jsonb or jsonb_typeof(request) is distinct from 'object' or request->>'model' is distinct from 'gpt-5.4-2026-03-05' or request->'background' is distinct from 'true'::jsonb or request->'store' is distinct from 'true'::jsonb or request->>'max_output_tokens' is distinct from '64000' or jsonb_typeof(request->'instructions') is distinct from 'string' or length(request->>'instructions') not between 1 and 40000 or jsonb_typeof(request->'input') is distinct from 'string' or octet_length(request::text)>300000 or request-array['model','instructions','input','background','store','reasoning','max_output_tokens','text']<>'{}'::jsonb or request->'text'->'format'->>'name' is distinct from 'paper_terminal_commands_v1' then raise exception 'A bounded server-side command-generation request is required';end if;
  if v_layout='per-step-v1' and (
   request#>>'{text,format,schema,properties,setup,properties,commands,type}' is distinct from 'null'
   or request#>'{text,format,schema,properties,setup,properties,kind,enum}' is distinct from '["manual"]'::jsonb
   or request#>>'{text,format,schema,properties,setup,properties,prerequisites,maxItems}' is distinct from '0'
   or request#>'{text,format,schema,properties,setup,properties,needs_sudo,enum}' is distinct from '[false]'::jsonb
   or request#>'{text,format,schema,properties,cleanup,properties,prerequisites,items,enum}' is distinct from public.research_terminal_action_refs(source_plan,p_index)
   or exists(select 1 from jsonb_each(request#>'{text,format,schema,properties,actions,properties}') a where a.value#>'{properties,prerequisites,items,enum}' is distinct from public.research_terminal_action_refs(source_plan,p_index))
  ) then raise exception 'Per-step commands must supply their own code without a shared setup';end if;
  if (request->>'input')::jsonb is distinct from public.research_terminal_commands_input(p_study,p_index,source_plan,p.confirmed_breakdown) then raise exception 'Generate commands only from the exact saved experiment';end if;
  select * into w from public.research_autonomy_workflows where study_id=p_study;
  if found then spent=w.committed_cents;select coalesce(sum(attempts),0) into calls from public.research_autonomy_tasks where study_id=p_study;end if;
  select coalesce(sum(reserved_cents),0),coalesce(sum(model_calls),0) into reserved,prior_calls from public.research_terminal_commands where study_id=p_study;
  select spent+reserved_cents, calls+model_calls into spent,calls from public.research_paper_intakes where study_id=p_study;
  spent=spent+p.reserved_cents+reserved;calls=calls+p.model_calls+prior_calls;
  if w.study_id is not null and w.max_spend_cents is not null and spent+200>w.max_spend_cents then raise exception 'The original assessment spending limit does not admit command generation';end if;
  if not public.autonomy_budget_allows('research_assessment',spent,calls,200,1) then raise exception 'The assessment budget does not admit command generation';end if;
  insert into public.research_terminal_commands(study_id,owner_id,experiment_index,target,command_layout,plan_revision,link_review_id,source_plan,confirmed_breakdown,status,submit_token,request,model_calls,reserved_cents,policy_snapshot,deadline_at,reason)
   values(p_study,p_actor,p_index,'ubuntu-debian',v_layout,p.revision,r.id,source_plan,p.confirmed_breakdown,'submitting',gen_random_uuid(),request,1,200,public.autonomy_assessment_budget_terms(),p.deadline_at,'Submitting terminal command generation.') returning * into c;
  configuration=request-array['input','instructions'];template='{"phase":"paper-terminal-commands-v1","target":"ubuntu-debian","study_id":"{{assessment_id}}","experiment_index":"{{experiment_number}}","confirmed":"{{confirmed_paper_sections}}","experiment":"{{saved_experiment_stages_and_actions}}"}'::jsonb;
  content=jsonb_build_object('instructions',request->>'instructions','input_template',template,'request_configuration',configuration);hash=encode(sha256(convert_to(content::text,'UTF8')),'hex');
  insert into public.research_paper_prompt_versions(version,instructions,input_template,request_configuration,content_sha256,created_at) values('paper-assessment-'||hash,request->>'instructions',template,configuration,hash,c.created_at) on conflict(content_sha256) do nothing;
  select id into strict prompt from public.research_paper_prompt_versions where content_sha256=hash;
  insert into public.research_terminal_command_prompt_uses(command_id,study_id,prompt_version_id,request_sha256) values(c.id,p_study,prompt,encode(sha256(convert_to(request::text,'UTF8')),'hex'));
  insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'generate-terminal-commands',jsonb_build_object('command_id',c.id,'experiment_index',p_index,'command_layout',v_layout,'model_calls',1,'experiments_started',0));
  return to_jsonb(c)||'{"admitted":true}'::jsonb;
 end if;
 if c.id is null or c.submit_token is distinct from (p_payload->>'token')::uuid then raise exception 'The original command call token is required';end if;
 if p_operation='submitted' then
  if c.provider_response_id is not null then if c.provider_response_id is distinct from p_payload->>'response_id' then raise exception 'Original provider identity cannot change';end if;return to_jsonb(c);end if;
  if c.status not in ('submitting','uncertain') or coalesce(p_payload->>'response_id','') !~ '^resp_[A-Za-z0-9_-]{1,200}$' then raise exception 'Original submitting command call required';end if;
  update public.research_terminal_commands set status='processing',provider_response_id=p_payload->>'response_id',response=p_payload->'response',reason='Generating terminal commands.' where id=c.id returning * into c;return to_jsonb(c);
 end if;
 if c.status in ('ready','failed','cancelled') then return to_jsonb(c);end if;
 if p_operation='uncertain' then
  if c.provider_response_id is not null then return to_jsonb(c);end if;
  update public.research_terminal_commands set status='uncertain',reason=left(p_payload->>'reason',2000) where id=c.id returning * into c;return to_jsonb(c);
 end if;
 if p_operation='finish' then
  if c.status<>'processing' or c.provider_response_id is distinct from p_payload->>'response_id' or p_payload->'response'->>'id' is distinct from c.provider_response_id or p_payload->'response'->>'status' is distinct from 'completed' or not (case when v_layout='per-step-v1' then public.research_valid_standalone_terminal_commands(p_payload->'command_set',public.research_terminal_action_refs(c.source_plan,c.experiment_index),public.research_terminal_blocked_refs(c.source_plan,c.experiment_index,c.confirmed_breakdown)) else public.research_valid_terminal_commands(p_payload->'command_set',public.research_terminal_action_refs(c.source_plan,c.experiment_index),public.research_terminal_blocked_refs(c.source_plan,c.experiment_index,c.confirmed_breakdown)) end) then raise exception 'Verified original response and a complete step-bound command set are required';end if;
  select string_agg(part.item->>'text','' order by message.position,part.position) into output
   from jsonb_array_elements(p_payload->'response'->'output') with ordinality message(item,position)
   cross join lateral jsonb_array_elements(case when message.item->>'type'='message' then message.item->'content' else '[]'::jsonb end) with ordinality part(item,position)
   where part.item->>'type'='output_text';
  if output::jsonb is distinct from p_payload->'command_set' then raise exception 'Retain the original generated command content';end if;
  update public.research_terminal_commands set status='ready',command_set=p_payload->'command_set',response=p_payload->'response',generated_at=clock_timestamp(),reason=null where id=c.id returning * into c;return to_jsonb(c);
 end if;
 if p_operation in ('failed','cancel') then
  if p_operation='cancel' and (c.provider_response_id is null or p_payload->'response'->>'id' is distinct from c.provider_response_id or p_payload->'response'->>'status' is distinct from 'cancelled') then raise exception 'Confirmed provider cancellation required';end if;
  if c.status='uncertain' then raise exception 'Reconcile the uncertain original command call first';end if;
  update public.research_terminal_commands set status=case when p_operation='cancel' then 'cancelled' else 'failed' end,response=coalesce(p_payload->'response',response),reason=left(p_payload->>'reason',2000) where id=c.id returning * into c;return to_jsonb(c);
 end if;raise exception 'Unknown terminal command operation';
end$$;

revoke all on function public.research_valid_standalone_terminal_commands(jsonb,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.research_valid_standalone_terminal_commands(jsonb,jsonb,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
