begin;
-- New work gets a separate approval gate. Originals and historical approvals are never rewritten.
create table if not exists public.research_paper_quality_workflows (
 id uuid primary key default gen_random_uuid(),study_id uuid not null references public.research_studies(id),owner_id uuid not null,
 step integer not null check(step in (2,3,4)),experiment_index integer not null default 0 check(experiment_index between 0 and 8),
 status text not null default 'waiting' check(status in ('waiting','review_pending','repair_pending','running','approved','needs_attention','uncertain','cancelled')),
 phase text not null default 'waiting' check(phase in ('waiting','reviewing','repairing','checking','approved','needs_attention','uncertain','cancelled')),
 round integer not null default 0 check(round in (0,1)),source_revision integer,source_provider_id text,source_json jsonb,original_request jsonb,candidate jsonb,
 review jsonb,checks jsonb,current_call_id uuid,reason text,deadline_at timestamptz not null,
 created_at timestamptz not null default clock_timestamp(),updated_at timestamptz not null default clock_timestamp(),
 unique(study_id,step,experiment_index),check((step=4)=(experiment_index>0)),check(status<>'approved' or candidate is not null and review->>'decision' is not distinct from 'pass' and checks->'passed' is not distinct from 'true'::jsonb)
);
create table if not exists public.research_paper_quality_calls (
 id uuid primary key default gen_random_uuid(),workflow_id uuid not null references public.research_paper_quality_workflows(id),study_id uuid not null,owner_id uuid not null,
 position integer not null check(position between 1 and 3),kind text not null check(kind in ('review','repair')),
 status text not null default 'preparing' check(status in ('preparing','submitting','processing','uncertain','completed','failed','cancelled')),
 source_sha256 text not null check(source_sha256 ~ '^[a-f0-9]{64}$'),submit_token uuid not null default gen_random_uuid(),request jsonb,provider_response_id text unique,response jsonb,
 model_calls integer not null default 1 check(model_calls=1),reserved_cents integer not null check(reserved_cents in (100,200)),policy_snapshot jsonb not null,deadline_at timestamptz not null,
 created_at timestamptz not null default clock_timestamp(),updated_at timestamptz not null default clock_timestamp(),unique(workflow_id,position),
 check((kind='repair')=(position=2)),check(provider_response_id is null or provider_response_id ~ '^resp_[A-Za-z0-9_-]{1,200}$')
);
create table if not exists public.research_paper_quality_events (
 id bigint generated always as identity primary key,workflow_id uuid not null references public.research_paper_quality_workflows(id),study_id uuid not null,
 kind text not null,snapshot jsonb not null,created_at timestamptz not null default clock_timestamp()
);
create table if not exists public.research_paper_quality_prompt_uses (
 call_id uuid primary key references public.research_paper_quality_calls(id),study_id uuid not null,prompt_version_id uuid not null references public.research_paper_prompt_versions(id),request_sha256 text not null,created_at timestamptz not null default clock_timestamp()
);
create index if not exists research_quality_owner_pending on public.research_paper_quality_workflows(owner_id,status,updated_at,id);
do $$declare t text;begin
 foreach t in array array['research_paper_quality_workflows','research_paper_quality_calls','research_paper_quality_events','research_paper_quality_prompt_uses'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role',t);
  execute format('grant select on public.%I to service_role',t);
 end loop;
end$$;
create or replace function public.research_quality_canonical(v jsonb) returns text language plpgsql immutable set search_path='' as $$
declare result text;begin
 case jsonb_typeof(v)
 when 'object' then select '{'||coalesce(string_agg(to_jsonb(key)::text||':'||public.research_quality_canonical(value),',' order by key collate "C"),'')||'}' into result from jsonb_each(v);
 when 'array' then select '['||coalesce(string_agg(public.research_quality_canonical(value),',' order by position),'')||']' into result from jsonb_array_elements(v) with ordinality a(value,position);
 when 'number' then result=trim_scale((v::text)::numeric)::text;
 else result=v::text;end case;return result;
end$$;
create or replace function public.research_quality_source(w public.research_paper_quality_workflows) returns jsonb language sql stable set search_path='' as $$
 select w.source_json||jsonb_build_object('candidate',w.candidate)
$$;
-- Counts every retained admission, including uncertain calls and quality reservations.
create or replace function public.research_assert_quality_budget(study uuid,cost integer,calls_delta integer) returns void language plpgsql set search_path='' as $$
declare spent bigint=0;calls bigint=0;original_limit bigint;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select coalesce(sum(reserved_cents),0),coalesce(sum(model_calls),0) into spent,calls from (
 select reserved_cents,model_calls from public.research_paper_intakes where study_id=study union all
 select reserved_cents,model_calls from public.research_experiment_plans where study_id=study union all
 select reserved_cents,model_calls from public.research_experiment_scripts where study_id=study union all
 select reserved_cents,model_calls from public.research_terminal_commands where study_id=study union all
 select reserved_cents,model_calls from public.research_step_commands where study_id=study union all
 select reserved_cents,model_calls from public.research_paper_quality_calls where study_id=study) admissions;
 select spent+committed_cents,max_spend_cents into spent,original_limit from public.research_autonomy_workflows where study_id=study;
 if not found then select coalesce(sum(reserved_cents),0) into spent from (
 select reserved_cents from public.research_paper_intakes where study_id=study union all select reserved_cents from public.research_experiment_plans where study_id=study union all select reserved_cents from public.research_experiment_scripts where study_id=study union all select reserved_cents from public.research_terminal_commands where study_id=study union all select reserved_cents from public.research_step_commands where study_id=study union all select reserved_cents from public.research_paper_quality_calls where study_id=study) a;end if;
 select calls+coalesce(sum(attempts),0) into calls from public.research_autonomy_tasks where study_id=study;
 if original_limit is not null and spent+cost>original_limit or not public.autonomy_budget_allows('research_assessment',spent,calls,cost,calls_delta) then raise exception 'The original assessment budget does not admit this generation or quality call';end if;
end$$;
create or replace function public.research_quality_admission_guard() returns trigger language plpgsql set search_path='' as $$
declare old_calls integer=0;old_cost integer=0;begin
 if tg_op='UPDATE' then old_calls=old.model_calls;old_cost=old.reserved_cents;end if;
 if new.model_calls>old_calls or new.reserved_cents>old_cost then perform public.research_assert_quality_budget(new.study_id,new.reserved_cents-old_cost,new.model_calls-old_calls);end if;
 return new;
end$$;
do $$declare t text;begin
 foreach t in array array['research_paper_intakes','research_experiment_plans','research_experiment_scripts','research_terminal_commands','research_step_commands'] loop
  execute format('drop trigger if exists a_quality_budget on public.%I',t);
  execute format('create trigger a_quality_budget before insert or update on public.%I for each row execute function public.research_quality_admission_guard()',t);
 end loop;
end$$;
create or replace function public.research_quality_mark_required() returns trigger language plpgsql set search_path='' as $$begin
 if tg_op='INSERT' then
  if tg_table_name<>'research_experiment_plans' or new.model_calls>0 then new.policy_snapshot=coalesce(new.policy_snapshot,'{}')||'{"quality_review":true}'::jsonb;end if;
 elsif old.policy_snapshot->'quality_review'='true'::jsonb then new.policy_snapshot=coalesce(new.policy_snapshot,'{}')||'{"quality_review":true}'::jsonb;
 end if;return new;
end$$;
create or replace function public.research_quality_capture_source() returns trigger language plpgsql security definer set search_path='' as $$
declare w public.research_paper_quality_workflows;j jsonb=to_jsonb(new);stage integer;idx integer=0;paper jsonb;context_breakdown jsonb;context_plan jsonb;draft jsonb;begin
 if new.policy_snapshot->'quality_review' is distinct from 'true'::jsonb then return new;end if;
 stage=case tg_table_name when 'research_paper_intakes' then 2 when 'research_experiment_plans' then 3 else 4 end;
 if stage=4 then idx=(j->>'experiment_index')::integer;end if;
 insert into public.research_paper_quality_workflows(study_id,owner_id,step,experiment_index,deadline_at) values(new.study_id,new.owner_id,stage,idx,new.deadline_at) on conflict(study_id,step,experiment_index) do nothing;
 select * into strict w from public.research_paper_quality_workflows where study_id=new.study_id and step=stage and experiment_index=idx for update;
 if w.status<>'waiting' then return new;end if;
 if new.status='ready' then
  if new.provider_response_id is null or j->'request' is null then raise exception 'A retained original provider call is required before automatic quality checking';end if;
  select paper_text into paper from public.research_paper_intakes where study_id=new.study_id;
  if stage=2 then draft=jsonb_build_object('breakdown',j->'breakdown','title',j->'title','authors',j->'authors','domain',j->'domain');context_breakdown='null';context_plan='null';
  elsif stage=3 then draft=j->'plan';context_breakdown=j->'confirmed_breakdown';context_plan='null';
  else draft=j->'command_set';context_breakdown=j->'confirmed_breakdown';context_plan=j->'source_plan';end if;
  update public.research_paper_quality_workflows set status='review_pending',phase='reviewing',source_revision=new.revision,source_provider_id=new.provider_response_id,
   source_json=jsonb_build_object('study_id',new.study_id,'step',stage,'experiment_index',idx,'paper',paper,'confirmed_breakdown',context_breakdown,'plan',context_plan,'candidate',draft),
   original_request=j->'request',candidate=draft,updated_at=clock_timestamp() where id=w.id;
 elsif new.status in ('failed','cancelled') then update public.research_paper_quality_workflows set status=case when new.status='cancelled' then 'cancelled' else 'needs_attention' end,phase=case when new.status='cancelled' then 'cancelled' else 'needs_attention' end,reason=new.reason,updated_at=clock_timestamp() where id=w.id;end if;
 return new;
end$$;
do $$declare t text;begin
 foreach t in array array['research_paper_intakes','research_experiment_plans','research_experiment_scripts'] loop
  execute format('drop trigger if exists a_quality_required on public.%I',t);
  execute format('create trigger a_quality_required before insert or update on public.%I for each row execute function public.research_quality_mark_required()',t);
  execute format('drop trigger if exists z_quality_source on public.%I',t);
  execute format('create trigger z_quality_source after insert or update on public.%I for each row execute function public.research_quality_capture_source()',t);
 end loop;
end$$;
create or replace function public.research_quality_history() returns trigger language plpgsql set search_path='' as $$begin
 if tg_op='DELETE' then raise exception 'Retain quality history';end if;
 if tg_table_name='research_paper_quality_workflows' then
  if tg_op='UPDATE' and ((new.id,new.study_id,new.owner_id,new.step,new.experiment_index,new.deadline_at,new.created_at) is distinct from (old.id,old.study_id,old.owner_id,old.step,old.experiment_index,old.deadline_at,old.created_at) or old.status in ('approved','needs_attention','cancelled') or old.source_json is not null and (new.source_json,new.original_request,new.source_revision,new.source_provider_id) is distinct from (old.source_json,old.original_request,old.source_revision,old.source_provider_id)) then raise exception 'Original quality source, terminal approval and limits are immutable';end if;
 else
  if tg_op='UPDATE' and ((new.id,new.workflow_id,new.study_id,new.owner_id,new.position,new.kind,new.source_sha256,new.submit_token,new.model_calls,new.reserved_cents,new.policy_snapshot,new.deadline_at,new.created_at) is distinct from (old.id,old.workflow_id,old.study_id,old.owner_id,old.position,old.kind,old.source_sha256,old.submit_token,old.model_calls,old.reserved_cents,old.policy_snapshot,old.deadline_at,old.created_at) or old.status in ('completed','failed','cancelled') or old.request is not null and new.request is distinct from old.request or old.provider_response_id is not null and new.provider_response_id is distinct from old.provider_response_id) then raise exception 'Original quality call and evidence are immutable';end if;
 end if;new.updated_at=clock_timestamp();return new;
end$$;
create or replace function public.research_quality_audit() returns trigger language plpgsql set search_path='' as $$begin
 insert into public.research_paper_quality_events(workflow_id,study_id,kind,snapshot) values(coalesce((to_jsonb(new)->>'workflow_id')::uuid,new.id),new.study_id,tg_table_name,to_jsonb(new)-array['source_json','original_request']);return new;
end$$;
do $$declare t text;begin
 foreach t in array array['research_paper_quality_workflows','research_paper_quality_calls'] loop
  execute format('drop trigger if exists quality_history on public.%I',t);
  execute format('create trigger quality_history before insert or update or delete on public.%I for each row execute function public.research_quality_history()',t);
  execute format('drop trigger if exists quality_audit on public.%I',t);
  execute format('create trigger quality_audit after insert or update on public.%I for each row execute function public.research_quality_audit()',t);
 end loop;
 foreach t in array array['research_paper_quality_events','research_paper_quality_prompt_uses'] loop
  execute format('drop trigger if exists quality_immutable on public.%I',t);
  execute format('create trigger quality_immutable before update or delete on public.%I for each row execute function public.research_immutable()',t);
 end loop;
end$$;
create or replace function public.research_valid_quality_review(v jsonb) returns boolean language plpgsql immutable set search_path='' as $$
declare f jsonb;begin
 if jsonb_typeof(v) is distinct from 'object' or not v ?& array['decision','summary','findings'] or v-array['decision','summary','findings']<>'{}'::jsonb or coalesce(v->>'decision','') not in ('pass','revise') or jsonb_typeof(v->'summary') is distinct from 'string' or length(btrim(v->>'summary')) not between 1 and 2000 or jsonb_typeof(v->'findings') is distinct from 'array' or jsonb_array_length(v->'findings')>30 then return false;end if;
 if (select count(*)<>count(distinct value->>'id') from jsonb_array_elements(v->'findings')) then return false;end if;
 for f in select value from jsonb_array_elements(v->'findings') loop
  if jsonb_typeof(f) is distinct from 'object' or not f ?& array['id','severity','location','explanation','evidence'] or f-array['id','severity','location','explanation','evidence']<>'{}'::jsonb or coalesce(f->>'severity','') not in ('blocking','warning') or
   exists(select 1 from jsonb_each(f) e where jsonb_typeof(e.value)<>'string') or length(btrim(f->>'id')) not between 1 and 80 or length(btrim(f->>'location')) not between 1 and 200 or length(btrim(f->>'explanation')) not between 1 and 2000 or length(btrim(f->>'evidence')) not between 1 and 2000 then return false;end if;
 end loop;
 return (v->>'decision'='revise')=exists(select 1 from jsonb_array_elements(v->'findings') item where item->>'severity'='blocking');
end$$;
create or replace function public.research_valid_quality_candidate(w public.research_paper_quality_workflows,v jsonb) returns boolean language plpgsql set search_path='' as $$
declare b jsonb;entry jsonb;section text;begin
 if w.step=3 then return public.research_valid_experiment_plan(v,w.source_json->'confirmed_breakdown');end if;
 if w.step=4 then return public.research_valid_experiment_scripts(v,w.source_json->'plan',w.experiment_index,w.source_json->'confirmed_breakdown');end if;
 if jsonb_typeof(v) is distinct from 'object' or not v ?& array['breakdown','title','authors','domain'] or v-array['breakdown','title','authors','domain']<>'{}'::jsonb or octet_length(v::text)>300000 or jsonb_typeof(v->'authors') is distinct from 'array' or jsonb_array_length(v->'authors')>100 then return false;end if;
 if exists(select 1 from jsonb_array_elements(v->'authors') a where jsonb_typeof(a)<>'string' or length(btrim(a#>>'{}')) not between 1 and 200) then return false;end if;
 b=v->'breakdown';
 if jsonb_typeof(b) is distinct from 'object' or (b-array['sections','provenance','implementation_choices']) is distinct from ((w.source_json->'candidate'->'breakdown')-array['sections','provenance','implementation_choices']) or jsonb_typeof(b->'sections') is distinct from 'object' or (b->'sections')-array['access','experiment','data','validate']<>'{}'::jsonb then return false;end if;
 foreach section in array array['access','experiment','data','validate'] loop
  if jsonb_typeof(b->'sections'->section) is distinct from 'array' or jsonb_array_length(b->'sections'->section)>64 then return false;end if;
  for entry in select value from jsonb_array_elements(b->'sections'->section) loop
   if jsonb_typeof(entry->'description') is distinct from 'string' or length(btrim(entry->>'description')) not between 1 and 400 then return false;end if;
   perform public.research_assert_paper_citations(entry->'citations',w.source_json->'paper');
  end loop;
 end loop;
 perform public.research_assert_paper_dependencies(b);
 if b ? 'provenance' then perform public.research_assert_paper_citations(b->'provenance'->'citations',w.source_json->'paper',case when b->'provenance'->>'classification'='unspecified' then 0 else 1 end);end if;
 for entry in select value from jsonb_array_elements(coalesce(b->'implementation_choices','[]')) loop perform public.research_assert_paper_citations(entry->'citations',w.source_json->'paper');end loop;
 return true;
exception when others then return false;
end$$;
create or replace function public.research_quality_result(workflow uuid) returns jsonb language sql stable set search_path='' as $$
 select to_jsonb(w)||jsonb_build_object('call',(select to_jsonb(c) from public.research_paper_quality_calls c where c.id=w.current_call_id and c.workflow_id=w.id),'admitted',false) from public.research_paper_quality_workflows w where w.id=workflow
$$;
-- Accept only the whole unchanged checker, directly or in a fixed literal exec
-- envelope. Merely containing checker text in arbitrary code is insufficient.
create or replace function public.research_quality_checker_code(actual text,expected text) returns boolean language plpgsql immutable set search_path='' as $$
declare delimiter text;name text;begin
 actual=btrim(actual);expected=btrim(expected);
 if actual=expected then return true;end if;
 foreach delimiter in array array[repeat(chr(39),3),repeat(chr(34),3)] loop
  if actual='exec(r'||delimiter||E'\n'||expected||E'\n'||delimiter||')' then return true;end if;
  foreach name in array array['checker','checker_code'] loop
   if actual=name||' = r'||delimiter||E'\n'||expected||E'\n'||delimiter||E'\nns = {}\nexec('||name||', ns, ns)' then return true;end if;
  end loop;
 end loop;return false;
end$$;
create or replace function public.research_paper_quality_control(p_operation text,p_actor uuid,p_workflow uuid,p_payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
#variable_conflict use_variable
declare w public.research_paper_quality_workflows;c public.research_paper_quality_calls;request jsonb;input jsonb;response jsonb;report jsonb;checks jsonb;candidate jsonb;tool jsonb;proof jsonb;part jsonb;line text;output text;hash text;content jsonb;configuration jsonb;prompt uuid;position integer;cost integer;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into w from public.research_paper_quality_workflows where id=p_workflow for update;
 if p_actor is null or w.id is null or w.owner_id<>p_actor or public.research_assessment_deleted(w.study_id) or not exists(select 1 from public.research_study_owners where study_id=w.study_id and owner_id=p_actor) or not exists(select 1 from auth.users u join auth.identities a on a.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and a.provider='google') then raise exception 'Verified active Google assessment owner required';end if;
 if jsonb_typeof(p_payload) is distinct from 'object' or octet_length(p_payload::text)>4000000 then raise exception 'Bounded retained quality evidence required';end if;
 if w.status in ('approved','needs_attention','cancelled') then return public.research_quality_result(w.id);end if;
 select * into c from public.research_paper_quality_calls where id=w.current_call_id and workflow_id=w.id for update;
 if p_operation='admit' then
  if w.status not in ('review_pending','repair_pending') then return public.research_quality_result(w.id);end if;
  if w.deadline_at<=clock_timestamp() then raise exception 'The original assessment deadline has expired';end if;
  hash=encode(sha256(convert_to(public.research_quality_canonical(public.research_quality_source(w)),'UTF8')),'hex');
  if p_payload->>'source_sha256' is distinct from hash then raise exception 'Review only the exact retained draft and frozen inputs';end if;
  position=case when w.status='repair_pending' then 2 when w.round=1 then 3 else 1 end;
  if exists(select 1 from public.research_paper_quality_calls qc where qc.workflow_id=w.id and qc.position=position) then raise exception 'Retain the original quality admission';end if;
  cost=case when w.step=4 then 200 else 100 end;perform public.research_assert_quality_budget(w.study_id,cost,1);
  insert into public.research_paper_quality_calls(workflow_id,study_id,owner_id,position,kind,source_sha256,reserved_cents,policy_snapshot,deadline_at) values(w.id,w.study_id,w.owner_id,position,case when position=2 then 'repair' else 'review' end,hash,cost,public.autonomy_assessment_budget_terms(),w.deadline_at) returning * into c;
  update public.research_paper_quality_workflows set current_call_id=c.id,status='running',phase=case when position=2 then 'repairing' when w.step=4 then 'checking' else 'reviewing' end where id=w.id;
  return public.research_quality_result(w.id)||'{"admitted":true}'::jsonb;
 end if;
 if p_operation='cancel' and w.status in ('waiting','review_pending','repair_pending') then update public.research_paper_quality_workflows set status='cancelled',phase='cancelled',reason=left(p_payload->>'reason',2000) where id=w.id;return public.research_quality_result(w.id);end if;
 if p_operation='failed' and w.status in ('review_pending','repair_pending') then update public.research_paper_quality_workflows set status='needs_attention',phase='needs_attention',reason=left(p_payload->>'reason',2000) where id=w.id;return public.research_quality_result(w.id);end if;
 -- A delayed acknowledgement may arrive after a later phase was admitted.
 -- Reconcile only byte-identical evidence from the original completed call.
 if p_operation in ('reviewed','repaired') and exists(select 1 from public.research_paper_quality_calls prior where prior.workflow_id=w.id and prior.id::text=p_payload->>'call_id' and prior.submit_token::text=p_payload->>'token' and prior.status='completed' and prior.response=p_payload->'response') then return public.research_quality_result(w.id);end if;
 if c.id is null or c.id::text is distinct from p_payload->>'call_id' or c.submit_token::text is distinct from p_payload->>'token' then raise exception 'The original quality call identity and token are required';end if;
 if p_operation='request' then
  if c.request is not null then if c.request is distinct from p_payload->'request' then raise exception 'The original quality request cannot change';end if;return public.research_quality_result(w.id);end if;
  if c.status<>'preparing' or w.status<>'running' or w.deadline_at<=clock_timestamp() then raise exception 'A current reserved quality call is required';end if;
  request=p_payload->'request';input=(request->>'input')::jsonb;
  if jsonb_typeof(request) is distinct from 'object' or request->>'model' is distinct from 'gpt-5.4-2026-03-05' or request->'background' is distinct from 'true'::jsonb or request->'store' is distinct from 'true'::jsonb or request->'reasoning'->>'effort' is distinct from (case when c.kind='review' then 'high' else 'medium' end) or request->>'max_output_tokens' is distinct from (case when w.step=4 then '64000' else '32768' end) or jsonb_typeof(request->'instructions') is distinct from 'string' or length(request->>'instructions') not between 1 and 40000 or request-array['model','instructions','input','background','store','reasoning','max_output_tokens','text','tools','max_tool_calls','include']<>'{}'::jsonb or octet_length(request::text)>2000000 or request->'text'->'format'->>'type' is distinct from 'json_schema' or request->'text'->'format'->'strict' is distinct from 'true'::jsonb or input->>'version' is distinct from 'paper-quality-v1' or input->>'source_sha256' is distinct from c.source_sha256 then raise exception 'A bounded source-bound review or repair request is required';end if;
  if c.kind='repair' then
   if input->'original_input' is distinct from w.original_request->'input' or input->'previous_output' is distinct from w.candidate or input->'findings' is distinct from w.review->'findings' or input->'checks' is distinct from w.checks or request->'text' is distinct from w.original_request->'text' or request ? 'tools' then raise exception 'Repair only this draft from its original inputs and findings';end if;
  else
   if request->'text'->'format'->>'name' is distinct from 'paper_quality_review_v1' then raise exception 'Structured quality findings required';end if;
   if w.step<>4 then
    if input->'source' is distinct from public.research_quality_source(w) or request ? 'tools' then raise exception 'Review the original paper, frozen inputs and exact draft';end if;
   else
    if request->'tools'->0->>'type' is distinct from 'code_interpreter' or jsonb_array_length(request->'tools')<>1 or request->'tools'->0->'container'->>'type' is distinct from 'auto' or request->'tools'->0->'container'->>'memory_limit' is distinct from '1g' or request->'tools'->0->'container'->'network_policy' is distinct from '{"type":"disabled"}'::jsonb or jsonb_array_length(request->'tools'->0->'container'->'file_ids')<>1 or request->'tools'->0->'container'->'file_ids'->>0 !~ '^file-[A-Za-z0-9_-]{1,200}$' or request->'max_tool_calls' is distinct from '12'::jsonb or request->'include' is distinct from '["code_interpreter_call.outputs"]'::jsonb or input->>'attachment' is distinct from w.study_id::text||'-quality-4-'||w.experiment_index||'-'||c.source_sha256||'.json' then raise exception 'An isolated source-bound Step 4 checker is required';end if;
   end if;
  end if;
  update public.research_paper_quality_calls set request=request,status='submitting' where id=c.id;
  -- Generic catalogue only: provider file IDs, assessment IDs, input, drafts and
  -- findings stay in private call history, never the shared /prompts catalogue.
  configuration=request-array['input','instructions'];
  if w.step=4 and c.kind='review' then configuration=jsonb_set(configuration,'{tools}','[{"type":"code_interpreter","container":{"type":"auto","memory_limit":"1g","network_policy":{"type":"disabled"},"file_ids":["{{private_candidate_file}}"]}}]');end if;
  content=jsonb_build_object('instructions',replace(replace(request->>'instructions',w.study_id::text,'{{assessment_id}}'),c.source_sha256,'{{source_sha256}}'),'input_template',jsonb_build_object('phase','paper-quality-v1','source','{{original_paper_and_frozen_inputs}}','candidate','{{private_draft}}','findings','{{prior_quality_findings}}'),'request_configuration',configuration);
  hash=encode(sha256(convert_to(content::text,'UTF8')),'hex');
  insert into public.research_paper_prompt_versions(version,instructions,input_template,request_configuration,content_sha256,created_at) values('paper-assessment-'||hash,content->>'instructions',content->'input_template',configuration,hash,c.created_at) on conflict(content_sha256) do nothing;
  select id into strict prompt from public.research_paper_prompt_versions where content_sha256=hash;
  insert into public.research_paper_quality_prompt_uses(call_id,study_id,prompt_version_id,request_sha256) values(c.id,w.study_id,prompt,encode(sha256(convert_to(request::text,'UTF8')),'hex'));
  return public.research_quality_result(w.id);
 end if;
 if p_operation='submitted' then
  if c.provider_response_id is not null then if c.provider_response_id is distinct from p_payload->>'response_id' then raise exception 'Original quality provider identity cannot change';end if;return public.research_quality_result(w.id);end if;
  if c.status not in ('submitting','uncertain') or c.request is null or coalesce(p_payload->>'response_id','') !~ '^resp_[A-Za-z0-9_-]{1,200}$' or p_payload->'response'->>'id' is distinct from p_payload->>'response_id' then raise exception 'The original submitting quality call is required';end if;
  update public.research_paper_quality_calls set status='processing',provider_response_id=p_payload->>'response_id',response=p_payload->'response' where id=c.id;
  update public.research_paper_quality_workflows set status='running',phase=case when c.kind='repair' then 'repairing' when w.step=4 then 'checking' else 'reviewing' end where id=w.id;return public.research_quality_result(w.id);
 end if;
 if p_operation='uncertain' then
  if c.provider_response_id is not null then return public.research_quality_result(w.id);end if;
  update public.research_paper_quality_calls set status='uncertain' where id=c.id;
  update public.research_paper_quality_workflows set status='uncertain',phase='uncertain',reason=left(p_payload->>'reason',2000) where id=w.id;return public.research_quality_result(w.id);
 end if;
 response=p_payload->'response';
 if p_operation in ('reviewed','repaired') then
  if w.status<>'running' or c.status<>'processing' or c.provider_response_id is distinct from response->>'id' or response->>'status' is distinct from 'completed' then raise exception 'A completed original quality response is required';end if;
  select string_agg(part.item->>'text','' order by message.position,part.position) into output from jsonb_array_elements(response->'output') with ordinality message(item,position) cross join lateral jsonb_array_elements(case when message.item->>'type'='message' then message.item->'content' else '[]'::jsonb end) with ordinality part(item,position) where part.item->>'type'='output_text';
  checks=p_payload->'checks';
  if checks->>'version' is distinct from 'paper-quality-v1' or jsonb_typeof(checks->'passed') is distinct from 'boolean' then raise exception 'Retained deterministic checks required';end if;
  if p_operation='repaired' then
   candidate=p_payload->'candidate';
   if c.kind<>'repair' or c.position<>2 or not public.research_valid_quality_candidate(w,candidate) or checks->'passed' is distinct from 'true'::jsonb or checks->>'source_sha256' is distinct from encode(sha256(convert_to(public.research_quality_canonical(w.source_json||jsonb_build_object('candidate',candidate)),'UTF8')),'hex') or w.step<>2 and output::jsonb is distinct from candidate then raise exception 'A source-valid replacement from the original repair response is required';end if;
   update public.research_paper_quality_calls set status='completed',response=response where id=c.id;
   update public.research_paper_quality_workflows set candidate=candidate,checks=checks,round=1,status='review_pending',phase='reviewing',reason=null where id=w.id;return public.research_quality_result(w.id);
  end if;
  report=p_payload->'review';
  if c.kind<>'review' or not public.research_valid_quality_review(report) or output::jsonb is distinct from report or checks->>'source_sha256' is distinct from c.source_sha256 or not public.research_valid_quality_review(jsonb_build_object('decision',case when exists(select 1 from jsonb_array_elements(checks->'findings') f where f->>'severity'='blocking') then 'revise' else 'pass' end,'summary','Recorded checks.','findings',checks->'findings')) or checks->'passed'='true'::jsonb and exists(select 1 from jsonb_array_elements(checks->'findings') f where f->>'severity'='blocking') then raise exception 'The review and checks must match their original response and source';end if;
  if w.step=4 then
   select item into tool from jsonb_array_elements(response->'output') item where item->>'type'='code_interpreter_call' and item->>'status'='completed' and item->>'id'=checks->'sandbox'->>'call_id' and item->>'container_id'=checks->'sandbox'->>'container_id' and public.research_quality_checker_code(item->>'code',split_part(c.request->>'instructions',E'The program source is:\n',2));
   if tool is null then raise exception 'A completed original sandbox execution is required';end if;
   for part in select value from jsonb_array_elements(tool->'outputs') loop if part->>'type'='logs' then for line in select regexp_split_to_table(part->>'logs',E'\n') loop if line like 'JUMPSERVE_QUALITY_CHECKS_V1 %' then proof=substring(line from length('JUMPSERVE_QUALITY_CHECKS_V1 ')+1)::jsonb;end if;end loop;end if;end loop;
   if (checks->'sandbox') ? 'artifact' then
    part=checks->'sandbox'->'artifact';
    if part->>'path' is distinct from '/mnt/data/jumpserve-quality-'||c.source_sha256||'-result.json' or coalesce(part->>'file_id','') !~ '^cfile_[A-Za-z0-9_-]{1,200}$' or octet_length(part->>'content')>100000 or part->>'content_sha256' is distinct from encode(sha256(convert_to(part->>'content','UTF8')),'hex') then raise exception 'Source-bound original sandbox artifact required';end if;
    if proof is not null and proof is distinct from (part->>'content')::jsonb then raise exception 'Sandbox logs and artifact disagree';end if;
    proof=(part->>'content')::jsonb;
   end if;
   if proof is null or proof is distinct from checks->'sandbox'->'result' or proof->>'source_sha256' is distinct from c.source_sha256 or proof->>'platform' is distinct from 'Linux' or jsonb_typeof(proof->'passed') is distinct from 'boolean' or checks->'passed'='true'::jsonb and (proof->'passed' is distinct from 'true'::jsonb or proof->'behavior'->'exit_code' is distinct from '0'::jsonb or proof->'behavior'->'candidate_unchanged' is distinct from 'true'::jsonb or coalesce((proof->'behavior'->>'test_count')::integer,0)<6 or jsonb_typeof(proof->'syntax') is distinct from 'array' or jsonb_array_length(proof->'syntax')=0 or exists(select 1 from jsonb_array_elements(proof->'syntax') s where s->'passed' is distinct from 'true'::jsonb)) then raise exception 'The source-bound Linux checks are missing or failed';end if;
  end if;
  update public.research_paper_quality_calls set status='completed',response=response where id=c.id;
  if report->>'decision'='pass' and checks->'passed'='true'::jsonb and public.research_valid_quality_candidate(w,w.candidate) then
   update public.research_paper_quality_workflows set status='approved',phase='approved',review=report,checks=checks,reason=null where id=w.id;
  elsif w.round=0 then update public.research_paper_quality_workflows set status='repair_pending',phase='repairing',review=report,checks=checks,reason='Review found issues. One bounded repair will be reviewed again.' where id=w.id;
  else update public.research_paper_quality_workflows set status='needs_attention',phase='needs_attention',review=report,checks=checks,reason='Issues remain after the single repair and independent re-review.' where id=w.id;end if;
  return public.research_quality_result(w.id);
 end if;
 if p_operation in ('failed','cancel') then
  if c.status='uncertain' then raise exception 'Reconcile the original uncertain quality call first';end if;
  if p_operation='cancel' and (c.provider_response_id is null or response->>'id' is distinct from c.provider_response_id or response->>'status' is distinct from 'cancelled') then raise exception 'Confirmed original quality cancellation required';end if;
  if response is not null and response->>'id' is distinct from c.provider_response_id then raise exception 'Original quality response identity required';end if;
  update public.research_paper_quality_calls set status=case when p_operation='cancel' then 'cancelled' else 'failed' end,response=coalesce(response,research_paper_quality_calls.response) where id=c.id;
  update public.research_paper_quality_workflows set status=case when p_operation='cancel' then 'cancelled' else 'needs_attention' end,phase=case when p_operation='cancel' then 'cancelled' else 'needs_attention' end,reason=left(p_payload->>'reason',2000) where id=w.id;return public.research_quality_result(w.id);
 end if;
 raise exception 'Unknown quality operation';
end$$;
-- Database consumers enforce the same gate as the owner API. Approved overlays
-- replace only the effective output; the original source rows remain unchanged.
create or replace function public.research_quality_approved(study uuid,stage integer,idx integer) returns jsonb language plpgsql stable set search_path='' as $$
declare w public.research_paper_quality_workflows;required boolean;begin
 if stage=2 then select policy_snapshot->'quality_review'='true'::jsonb into required from public.research_paper_intakes where study_id=study;
 elsif stage=3 then select policy_snapshot->'quality_review'='true'::jsonb into required from public.research_experiment_plans where study_id=study;
 else select policy_snapshot->'quality_review'='true'::jsonb into required from public.research_experiment_scripts where study_id=study and experiment_index=idx;end if;
 if not coalesce(required,false) then return null;end if;
 select * into w from public.research_paper_quality_workflows where study_id=study and step=stage and experiment_index=idx;
 if w.id is null or w.status<>'approved' then raise exception 'Wait for the required quality review and checks before continuing';end if;
 return w.candidate;
end$$;
do $$declare body text;old text;replacement text;begin
 select prosrc into strict body from pg_proc where oid='public.research_experiment_plan(text,uuid,uuid,jsonb)'::regprocedure;
 -- Use dollar quoted anchors so migration application is explicit and repeatable.
 old=$anchor$ select * into p from public.research_experiment_plans where study_id=p_study for update;$anchor$;
 replacement=$anchor$ if p_operation='confirm' and i.policy_snapshot->'quality_review'='true'::jsonb then
  i.breakdown=public.research_quality_approved(p_study,2,0)->'breakdown';
 end if;
 select * into p from public.research_experiment_plans where study_id=p_study for update;$anchor$;
 if position('research_quality_approved' in body)=0 then
  if position(old in body)=0 then raise exception 'The current phase-one confirmation guard needs explicit review';end if;
  body=replace(body,old,replacement);
  execute 'create or replace function public.research_experiment_plan(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb default ''{}'') returns jsonb language plpgsql security definer set search_path='''' as '||quote_literal(body);
 end if;
 select prosrc into strict body from pg_proc where oid='public.research_experiment_scripts_control(text,uuid,uuid,integer,jsonb)'::regprocedure;
 old=$anchor$  if source_plan is null or not public.research_valid_experiment_plan(source_plan,p.confirmed_breakdown)$anchor$;
 replacement=$anchor$  if p.policy_snapshot->'quality_review'='true'::jsonb then source_plan=public.research_quality_approved(p_study,3,0);end if;
  if source_plan is null or not public.research_valid_experiment_plan(source_plan,p.confirmed_breakdown)$anchor$;
 if position('research_quality_approved' in body)=0 then
  if position(old in body)=0 then raise exception 'The current shared-script source guard needs explicit review';end if;
  body=replace(body,old,replacement);
  execute 'create or replace function public.research_experiment_scripts_control(p_operation text,p_actor uuid,p_study uuid,p_index integer,p_payload jsonb default ''{}'') returns jsonb language plpgsql security definer set search_path='''' as '||quote_literal(body);
 end if;
end$$;
create or replace function public.research_quality_pending_delete_guard() returns trigger language plpgsql set search_path='' as $$begin
 if old.deleted_at is null and new.deleted_at is not null and exists(select 1 from public.research_paper_quality_workflows where study_id=old.id and status not in ('approved','needs_attention','cancelled')) then raise exception 'Cancel or reconcile the retained quality calls before deleting this assessment';end if;return new;
end$$;
drop trigger if exists pending_paper_quality_delete on public.research_studies;
create trigger pending_paper_quality_delete before update of deleted_at on public.research_studies for each row execute function public.research_quality_pending_delete_guard();
do $$declare proc regprocedure;begin
 for proc in select oid::regprocedure from pg_proc where pronamespace='public'::regnamespace and proname in ('research_quality_canonical','research_quality_source','research_assert_quality_budget','research_quality_admission_guard','research_quality_mark_required','research_quality_capture_source','research_quality_history','research_quality_audit','research_valid_quality_review','research_valid_quality_candidate','research_quality_result','research_quality_checker_code','research_quality_approved','research_quality_pending_delete_guard','research_paper_quality_control') loop
  execute 'revoke all on function '||proc||' from public,anon,authenticated,service_role';
 end loop;
end$$;
grant execute on function public.research_paper_quality_control(text,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
