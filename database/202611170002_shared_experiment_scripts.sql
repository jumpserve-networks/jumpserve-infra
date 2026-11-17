begin;
-- Step 4 shared setup and full-experiment command packages. Historical experiment-wide
-- packages, requests, responses, confirmations, reservations and events remain
-- unchanged. Admission and all original limits are enforced atomically.
create table if not exists public.research_experiment_scripts (
 id uuid primary key default gen_random_uuid(),study_id uuid not null references public.research_experiment_plans(study_id),owner_id uuid not null,
 experiment_index integer not null check(experiment_index between 1 and 8),command_layout text not null default 'shared-setup-v2' check(command_layout='shared-setup-v2'),target text not null check(target='ubuntu-debian'),
 plan_revision integer not null,link_review_id uuid references public.research_experiment_plan_link_reviews(id),source_plan jsonb not null,confirmed_breakdown jsonb not null,
 status text not null check(status in ('submitting','processing','uncertain','ready','failed','cancelled')),
 submit_token uuid not null,provider_response_id text unique,request jsonb not null,response jsonb,command_set jsonb,reason text,generated_at timestamptz,
 model_calls integer not null check(model_calls=1),reserved_cents integer not null check(reserved_cents=200),policy_snapshot jsonb not null,deadline_at timestamptz not null,
 created_at timestamptz not null default clock_timestamp(),updated_at timestamptz not null default clock_timestamp(),revision integer not null default 1,
 unique(study_id,experiment_index,target),check(status<>'ready' or command_set is not null and generated_at is not null),
 check(provider_response_id is null or provider_response_id ~ '^resp_[A-Za-z0-9_-]{1,200}$')
);
create table if not exists public.research_experiment_script_events (
 id bigint generated always as identity primary key,command_id uuid not null references public.research_experiment_scripts(id),study_id uuid not null,
 revision integer not null,snapshot jsonb not null,created_at timestamptz not null default clock_timestamp(),unique(command_id,revision)
);
create table if not exists public.research_experiment_script_prompt_uses (
 command_id uuid primary key references public.research_experiment_scripts(id),study_id uuid not null,
 prompt_version_id uuid not null references public.research_paper_prompt_versions(id),request_sha256 text not null,recorded_at timestamptz not null default clock_timestamp()
);
alter table public.research_experiment_scripts enable row level security;
alter table public.research_experiment_script_events enable row level security;
alter table public.research_experiment_script_prompt_uses enable row level security;
revoke all on public.research_experiment_scripts,public.research_experiment_script_events,public.research_experiment_script_prompt_uses from public,anon,authenticated,service_role;
grant select on public.research_experiment_scripts,public.research_experiment_script_events,public.research_experiment_script_prompt_uses to service_role;
drop trigger if exists command_assessment_active on public.research_experiment_scripts;
create trigger command_assessment_active before insert or update on public.research_experiment_scripts for each row execute function public.research_require_active_assessment();
drop trigger if exists command_event_immutable on public.research_experiment_script_events;
create trigger command_event_immutable before update or delete on public.research_experiment_script_events for each row execute function public.research_immutable();
drop trigger if exists command_prompt_immutable on public.research_experiment_script_prompt_uses;
create trigger command_prompt_immutable before update or delete on public.research_experiment_script_prompt_uses for each row execute function public.research_immutable();
create or replace function public.research_experiment_script_history() returns trigger language plpgsql set search_path='' as $$begin
 if tg_op='DELETE' then raise exception 'Retain terminal command history';end if;
 if tg_op='UPDATE' then
  if (new.id,new.study_id,new.owner_id,new.experiment_index,new.command_layout,new.target,new.plan_revision,new.link_review_id,new.source_plan,new.confirmed_breakdown,new.submit_token,new.request,new.model_calls,new.reserved_cents,new.policy_snapshot,new.deadline_at,new.created_at)
   is distinct from (old.id,old.study_id,old.owner_id,old.experiment_index,old.command_layout,old.target,old.plan_revision,old.link_review_id,old.source_plan,old.confirmed_breakdown,old.submit_token,old.request,old.model_calls,old.reserved_cents,old.policy_snapshot,old.deadline_at,old.created_at)
   or old.status in ('ready','failed','cancelled') or old.provider_response_id is not null and new.provider_response_id is distinct from old.provider_response_id
  then raise exception 'Original command scope, request, provider identity, terminal result and limits are immutable';end if;
  new.revision=old.revision+1;new.updated_at=clock_timestamp();
 end if;return new;
end$$;
drop trigger if exists command_history on public.research_experiment_scripts;
create trigger command_history before insert or update or delete on public.research_experiment_scripts for each row execute function public.research_experiment_script_history();
create or replace function public.research_experiment_script_audit() returns trigger language plpgsql set search_path='' as $$begin
 insert into public.research_experiment_script_events(command_id,study_id,revision,snapshot) values(new.id,new.study_id,new.revision,to_jsonb(new));return new;
end$$;
drop trigger if exists command_audit on public.research_experiment_scripts;
create trigger command_audit after insert or update on public.research_experiment_scripts for each row execute function public.research_experiment_script_audit();
create or replace function public.research_pending_experiment_script_delete_guard() returns trigger language plpgsql set search_path='' as $$begin
 if old.deleted_at is null and new.deleted_at is not null and exists(select 1 from public.research_experiment_scripts c where c.study_id=old.id and c.status in ('submitting','processing','uncertain')) then raise exception 'Cancel or reconcile the original terminal command generation before deleting this assessment';end if;return new;
end$$;
drop trigger if exists pending_experiment_script_delete on public.research_studies;
create trigger pending_experiment_script_delete before update of deleted_at on public.research_studies for each row execute function public.research_pending_experiment_script_delete_guard();



create or replace function public.research_experiment_scripts_input(study uuid,n integer,p jsonb,b jsonb) returns jsonb language sql immutable set search_path='' as $$
 select public.research_terminal_commands_input(study,n,p,b)||jsonb_build_object('phase','paper-experiment-scripts-v1','command_layout','shared-setup-v2')
$$;
create or replace function public.research_complete_script(commands text) returns boolean language plpgsql immutable set search_path='' as $$
declare line text;closing text=null;tabs boolean=false;m text[];begin
 if commands is null then return false;end if;
 for line in select regexp_split_to_table(commands,E'\r?\n') loop
  if closing is not null then
   if (case when tabs then regexp_replace(line,E'^\t+','') else line end)=closing then closing=null;end if;
  else
   m=regexp_match(line,$pattern$(^|[^<])<<(?!<)(-?)[ \t]*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\3$pattern$);
   if m is not null then closing=m[4];tabs=m[2]='-';end if;
  end if;
 end loop;
 return closing is null;
end$$;
-- Validate the entire large setup without truncation; historical validators retain their bounds.
create or replace function public.research_valid_shared_command_set(v jsonb,refs jsonb,blocked jsonb default '[]') returns boolean language plpgsql immutable set search_path='' as $$
declare block jsonb;entry jsonb;ref text;names text[]='{}';allowed text[]='{}';expected text[];begin
 if jsonb_typeof(v) is distinct from 'object' or not v ?& array['setup','actions','cleanup','inputs'] or v-array['setup','actions','cleanup','inputs']<>'{}'::jsonb or octet_length(v::text)>250000 or jsonb_typeof(v->'actions') is distinct from 'object' or jsonb_typeof(v->'inputs') is distinct from 'array' then return false;end if;
 select coalesce(array_agg(value),'{}'::text[]) into expected from jsonb_array_elements_text(refs);
 if (v->'actions')-expected<>'{}'::jsonb or (select count(*) from jsonb_object_keys(v->'actions'))<>cardinality(expected) or jsonb_array_length(v->'inputs')>16 then return false;end if;
 for entry in select value from jsonb_array_elements(v->'inputs') loop
  if jsonb_typeof(entry) is distinct from 'object' or not entry ?& array['name','description','secret'] or entry-array['name','description','secret']<>'{}'::jsonb or jsonb_typeof(entry->'name') is distinct from 'string' or coalesce(entry->>'name','') !~ '^JUMPSERVE_[A-Z][A-Z0-9_]{0,63}$' or entry->>'name'=any(names) or jsonb_typeof(entry->'description') is distinct from 'string' or length(btrim(entry->>'description')) not between 1 and 600 or jsonb_typeof(entry->'secret') is distinct from 'boolean' then return false;end if;
  names=array_append(names,entry->>'name');
 end loop;
 foreach ref in array array['setup']||expected||array['cleanup'] loop
  block=case when ref in ('setup','cleanup') then v->ref else v->'actions'->ref end;
  if jsonb_typeof(block) is distinct from 'object' or not block ?& array['kind','commands','prerequisites','verification','notes','needs_sudo'] or block-array['kind','commands','prerequisites','verification','notes','needs_sudo']<>'{}'::jsonb or coalesce(block->>'kind','') not in ('terminal','manual','blocked') or jsonb_typeof(block->'needs_sudo') is distinct from 'boolean' or jsonb_typeof(block->'verification') is distinct from 'string' or length(btrim(block->>'verification')) not between 1 and 800 or jsonb_typeof(block->'notes') is distinct from 'string' or length(btrim(block->>'notes')) not between 1 and 1200 or jsonb_typeof(block->'prerequisites') is distinct from 'array' then return false;end if;
  if jsonb_array_length(block->'prerequisites')>24 or exists(select 1 from jsonb_array_elements(block->'prerequisites') r where jsonb_typeof(r) is distinct from 'string') or exists(select 1 from jsonb_array_elements_text(block->'prerequisites') r where not r.value=any(allowed)) or (select count(*)<>count(distinct value) from jsonb_array_elements_text(block->'prerequisites')) then return false;end if;
  if block->>'kind'='terminal' then
   if jsonb_typeof(block->'commands') is distinct from 'string' or length(btrim(block->>'commands')) not between 1 and (case when ref='setup' then 200000 else 16000 end) then return false;end if;
   if (block->>'commands') ~ E'(^|[;\\n&|])[[:space:]]*(sudo[[:space:]]+)?tc[[:space:]]+(qdisc|class|filter)[[:space:]]+(add|change|replace|del|delete)([[:space:]]|$)' then return false;end if;
   if (block->>'commands') like '%python3-distutils%' then return false;end if;
  elsif block->'commands' is distinct from 'null'::jsonb or block->'needs_sudo' is distinct from 'false'::jsonb then return false;end if;
  if blocked ? ref and block->>'kind'<>'blocked' then return false;end if;
  allowed=array_append(allowed,ref);
 end loop;return true;
end$$;
create or replace function public.research_valid_experiment_scripts(v jsonb,p jsonb,n integer,b jsonb) returns boolean language plpgsql immutable set search_path='' as $$
declare block jsonb;ref text;begin
 if public.research_valid_shared_command_set(v,public.research_terminal_action_refs(p,n),public.research_terminal_blocked_refs(p,n,b)) is not true then return false;end if;
 if v->'setup'->'prerequisites' is distinct from '[]'::jsonb then return false;end if;
 for ref,block in select 'setup',v->'setup' union all select key,value from jsonb_each(v->'actions') union all select 'cleanup',v->'cleanup' loop
  if block->>'kind'='terminal' then
   if ref<>'setup' and (v->'setup'->>'kind'<>'terminal' or not (block->'prerequisites') ? 'setup') then return false;end if;
   if not public.research_complete_script(block->>'commands') then return false;end if;
   if (block->>'commands') ~ $rx$(os[.]readlink|open)[[:space:]]*[(][[:space:]]*f?['"]/proc/[{][^}]+[}]/(exe|cmdline|ns/net)['"]$rx$ then return false;end if;
  end if;
 end loop;
 return true;
end$$;
create or replace function public.research_experiment_scripts_control(p_operation text,p_actor uuid,p_study uuid,p_index integer,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare p public.research_experiment_plans;c public.research_experiment_scripts;r public.research_experiment_plan_link_reviews;w public.research_autonomy_workflows;
 source_plan jsonb;request jsonb;configuration jsonb;template jsonb;content jsonb;hash text;prompt uuid;output text;spent bigint=0;calls bigint=0;reserved bigint=0;prior_calls bigint=0;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or public.research_assessment_deleted(p_study) or not exists(select 1 from auth.users u join auth.identities a on a.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and a.provider='google') then raise exception 'Verified active Google owner required';end if;
 select * into p from public.research_experiment_plans where study_id=p_study for update;
 if p.study_id is null or p.owner_id<>p_actor or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private assessment not found';end if;
 if p_index is null or p_index not between 1 and 8 or jsonb_typeof(p_payload) is distinct from 'object' or octet_length(p_payload::text)>1500000 then raise exception 'Bounded experiment command request required';end if;
 select * into c from public.research_experiment_scripts where study_id=p_study and experiment_index=p_index and target='ubuntu-debian' for update;
 if p_operation='generate' then
  if c.id is not null then return to_jsonb(c)||'{"admitted":false}'::jsonb;end if;
  if p.status='ready' then source_plan=p.plan;
  elsif p.status='failed' then select * into r from public.research_experiment_plan_link_reviews where study_id=p_study and owner_id=p_actor and base_revision=p.revision and provider_response_id=p.provider_response_id;source_plan=r.plan;
  end if;
  if source_plan is null or not public.research_valid_experiment_plan(source_plan,p.confirmed_breakdown) or p_index>jsonb_array_length(source_plan->'experiments') then raise exception 'A saved ready experiment plan is required';end if;
  if exists(select 1 from public.research_terminal_commands where study_id=p_study and experiment_index=p_index and status in ('submitting','processing','uncertain')) or exists(select 1 from public.research_step_commands where study_id=p_study and experiment_index=p_index and status in ('submitting','processing','uncertain')) then raise exception 'Reconcile or cancel earlier command requests before shared setup generation';end if;
  if p.deadline_at<=clock_timestamp() then raise exception 'The original assessment deadline has expired';end if;
  request=p_payload->'request';
  if p_payload-array['request']<>'{}'::jsonb or jsonb_typeof(request) is distinct from 'object' or request->>'model' is distinct from 'gpt-5.4-2026-03-05' or request->'background' is distinct from 'true'::jsonb or request->'store' is distinct from 'true'::jsonb or request->>'max_output_tokens' is distinct from '64000' or jsonb_typeof(request->'instructions') is distinct from 'string' or length(request->>'instructions') not between 1 and 40000 or jsonb_typeof(request->'input') is distinct from 'string' or octet_length(request::text)>300000 or request-array['model','instructions','input','background','store','reasoning','max_output_tokens','text']<>'{}'::jsonb or request->'text'->'format'->>'name' is distinct from 'paper_experiment_scripts_v1' then raise exception 'A bounded server-side command-generation request is required';end if;
  if (request->>'input')::jsonb is distinct from public.research_experiment_scripts_input(p_study,p_index,source_plan,p.confirmed_breakdown) then raise exception 'Generate commands only from the exact saved experiment';end if;
  if octet_length(request->>'input')>100000 or request->'max_output_tokens' is distinct from '64000'::jsonb or request->'reasoning'->>'effort' is distinct from 'medium' or
   request->'text'->'format'->>'type' is distinct from 'json_schema' or request->'text'->'format'->'strict' is distinct from 'true'::jsonb or
   request->'text'->'format'->'schema'->'properties'->'actions'->'required' is distinct from public.research_terminal_action_refs(source_plan,p_index) or
   jsonb_typeof(request->'text'->'format'->'schema'->'properties'->'actions'->'properties') is distinct from 'object' or
   (request->'text'->'format'->'schema'->'properties'->'actions'->'properties')-array(select jsonb_array_elements_text(public.research_terminal_action_refs(source_plan,p_index)))<>'{}'::jsonb or
   (select count(*) from jsonb_object_keys(request->'text'->'format'->'schema'->'properties'->'actions'->'properties'))<>jsonb_array_length(public.research_terminal_action_refs(source_plan,p_index)) or
   request->'text'->'format'->'schema'->'properties'->'setup'->'properties'->'commands'->'maxLength' is distinct from '200000'::jsonb then raise exception 'Request a complete shared setup and exactly the saved numbered actions';end if;
  select * into w from public.research_autonomy_workflows where study_id=p_study;
  if found then spent=w.committed_cents;select coalesce(sum(attempts),0) into calls from public.research_autonomy_tasks where study_id=p_study;end if;
  select coalesce(sum(reserved_cents),0),coalesce(sum(model_calls),0) into reserved,prior_calls from (select reserved_cents,model_calls from public.research_terminal_commands where study_id=p_study union all select reserved_cents,model_calls from public.research_experiment_scripts where study_id=p_study union all select reserved_cents,model_calls from public.research_step_commands where study_id=p_study) prior;
  select spent+reserved_cents, calls+model_calls into spent,calls from public.research_paper_intakes where study_id=p_study;
  spent=spent+p.reserved_cents+reserved;calls=calls+p.model_calls+prior_calls;
  if w.study_id is not null and w.max_spend_cents is not null and spent+200>w.max_spend_cents then raise exception 'The original assessment spending limit does not admit command generation';end if;
  if not public.autonomy_budget_allows('research_assessment',spent,calls,200,1) then raise exception 'The assessment budget does not admit command generation';end if;
  insert into public.research_experiment_scripts(study_id,owner_id,experiment_index,target,plan_revision,link_review_id,source_plan,confirmed_breakdown,status,submit_token,request,model_calls,reserved_cents,policy_snapshot,deadline_at,reason)
   values(p_study,p_actor,p_index,'ubuntu-debian',p.revision,r.id,source_plan,p.confirmed_breakdown,'submitting',gen_random_uuid(),request,1,200,public.autonomy_assessment_budget_terms(),p.deadline_at,'Submitting terminal command generation.') returning * into c;
  configuration=request-array['input','instructions'];template='{"phase":"paper-experiment-scripts-v1","command_layout":"shared-setup-v2","target":"ubuntu-debian","study_id":"{{assessment_id}}","experiment_index":"{{experiment_number}}","confirmed":"{{confirmed_paper_sections}}","experiment":"{{saved_experiment_stages_and_actions}}"}'::jsonb;
  content=jsonb_build_object('instructions',request->>'instructions','input_template',template,'request_configuration',configuration);hash=encode(sha256(convert_to(content::text,'UTF8')),'hex');
  insert into public.research_paper_prompt_versions(version,instructions,input_template,request_configuration,content_sha256,created_at) values('paper-assessment-'||hash,request->>'instructions',template,configuration,hash,c.created_at) on conflict(content_sha256) do nothing;
  select id into strict prompt from public.research_paper_prompt_versions where content_sha256=hash;
  insert into public.research_experiment_script_prompt_uses(command_id,study_id,prompt_version_id,request_sha256) values(c.id,p_study,prompt,encode(sha256(convert_to(request::text,'UTF8')),'hex'));
  insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'generate-experiment-scripts',jsonb_build_object('command_id',c.id,'experiment_index',p_index,'model_calls',1,'experiments_started',0));
  return to_jsonb(c)||'{"admitted":true}'::jsonb;
 end if;
 if c.id is null or c.submit_token is distinct from (p_payload->>'token')::uuid then raise exception 'The original command call token is required';end if;
 if p_operation='submitted' then
  if c.provider_response_id is not null then if c.provider_response_id is distinct from p_payload->>'response_id' then raise exception 'Original provider identity cannot change';end if;return to_jsonb(c);end if;
  if c.status not in ('submitting','uncertain') or coalesce(p_payload->>'response_id','') !~ '^resp_[A-Za-z0-9_-]{1,200}$' then raise exception 'Original submitting command call required';end if;
  update public.research_experiment_scripts set status='processing',provider_response_id=p_payload->>'response_id',response=p_payload->'response',reason='Generating terminal commands.' where id=c.id returning * into c;return to_jsonb(c);
 end if;
 if c.status in ('ready','failed','cancelled') then return to_jsonb(c);end if;
 if p_operation='uncertain' then
  if c.provider_response_id is not null then return to_jsonb(c);end if;
  update public.research_experiment_scripts set status='uncertain',reason=left(p_payload->>'reason',2000) where id=c.id returning * into c;return to_jsonb(c);
 end if;
 if p_operation='finish' then
  if c.status<>'processing' or c.provider_response_id is distinct from p_payload->>'response_id' or p_payload->'response'->>'id' is distinct from c.provider_response_id or p_payload->'response'->>'status' is distinct from 'completed' or not public.research_valid_experiment_scripts(p_payload->'command_set',c.source_plan,c.experiment_index,c.confirmed_breakdown) then raise exception 'Verified original response and complete shared experiment scripts are required';end if;
  select string_agg(part.item->>'text','' order by message.position,part.position) into output
   from jsonb_array_elements(p_payload->'response'->'output') with ordinality message(item,position)
   cross join lateral jsonb_array_elements(case when message.item->>'type'='message' then message.item->'content' else '[]'::jsonb end) with ordinality part(item,position)
   where part.item->>'type'='output_text';
  if output::jsonb is distinct from p_payload->'command_set' then raise exception 'Retain the original generated command content';end if;
  update public.research_experiment_scripts set status='ready',command_set=p_payload->'command_set',response=p_payload->'response',generated_at=clock_timestamp(),reason=null where id=c.id returning * into c;return to_jsonb(c);
 end if;
 if p_operation in ('failed','cancel') then
  if p_operation='cancel' and (c.provider_response_id is null or p_payload->'response'->>'id' is distinct from c.provider_response_id or p_payload->'response'->>'status' is distinct from 'cancelled') then raise exception 'Confirmed provider cancellation required';end if;
  if c.status='uncertain' then raise exception 'Reconcile the uncertain original command call first';end if;
  update public.research_experiment_scripts set status=case when p_operation='cancel' then 'cancelled' else 'failed' end,response=coalesce(p_payload->'response',response),reason=left(p_payload->>'reason',2000) where id=c.id returning * into c;return to_jsonb(c);
 end if;raise exception 'Unknown terminal command operation';
end$$;


-- Older individual requests retain read/reconciliation/cancellation and immutable
-- history. New generation belongs exclusively to the Step 4 package.
do $$begin
 if to_regprocedure('public.research_step_commands_control_before_shared_scripts(text,uuid,uuid,integer,text,jsonb)') is null then
  alter function public.research_step_commands_control(text,uuid,uuid,integer,text,jsonb) rename to research_step_commands_control_before_shared_scripts;
 end if;
end$$;
create or replace function public.research_step_commands_control(p_operation text,p_actor uuid,p_study uuid,p_index integer,p_ref text,p_payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$begin
 if p_operation='generate' then raise exception 'Generate the shared setup and experiment commands in Step 4';end if;
 return public.research_step_commands_control_before_shared_scripts(p_operation,p_actor,p_study,p_index,p_ref,p_payload);
end$$;
revoke all on function public.research_step_commands_control_before_shared_scripts(text,uuid,uuid,integer,text,jsonb) from public,anon,authenticated,service_role;
revoke all on function public.research_step_commands_control(text,uuid,uuid,integer,text,jsonb),public.research_experiment_scripts_input(uuid,integer,jsonb,jsonb),public.research_complete_script(text),public.research_valid_shared_command_set(jsonb,jsonb,jsonb),public.research_valid_experiment_scripts(jsonb,jsonb,integer,jsonb),public.research_experiment_scripts_control(text,uuid,uuid,integer,jsonb),public.research_experiment_script_history(),public.research_experiment_script_audit(),public.research_pending_experiment_script_delete_guard() from public,anon,authenticated;
grant execute on function public.research_step_commands_control(text,uuid,uuid,integer,text,jsonb),public.research_experiment_scripts_input(uuid,integer,jsonb,jsonb),public.research_complete_script(text),public.research_valid_shared_command_set(jsonb,jsonb,jsonb),public.research_valid_experiment_scripts(jsonb,jsonb,integer,jsonb),public.research_experiment_scripts_control(text,uuid,uuid,integer,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
