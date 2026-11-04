begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

create table public.platform_capability_requests (
 id uuid primary key,parent_task_id uuid not null references public.platform_tasks(id),
 implementation_task_id uuid not null unique references public.platform_tasks(id),
 capability_id text not null check(capability_id ~ '^[a-z][a-z0-9-]{1,62}$'),
 minimum_revision integer not null check(minimum_revision between 1 and 1000000),
 spec jsonb not null,spec_sha256 text not null check(spec_sha256 ~ '^[a-f0-9]{64}$'),
 artifact_id uuid not null references public.platform_artifacts(id),
 created_at timestamptz not null default clock_timestamp(),
 unique(parent_task_id,spec_sha256),check(parent_task_id<>implementation_task_id),
 check(octet_length(spec::text)<=16000)
);
create table public.platform_capability_activations (
 request_id uuid primary key references public.platform_capability_requests(id),
 supervisor_activation_id uuid not null references public.platform_supervisor_activations(id),
 capability_id text not null,revision integer not null check(revision between 1 and 1000000),
 module_sha256 text not null check(module_sha256 ~ '^[a-f0-9]{64}$'),
 source_revision text not null check(source_revision ~ '^[a-f0-9]{40}$'),
 created_at timestamptz not null default clock_timestamp()
);
do $$declare name text;begin
 foreach name in array array['platform_capability_requests','platform_capability_activations'] loop
  execute format('alter table public.%I enable row level security',name);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role',name);
  execute format('grant select on public.%I to service_role',name);
  execute format('create trigger %I before update or delete on public.%I for each row execute function public.platform_immutable()',name||'_immutable',name);
 end loop;
end$$;

create function public.platform_capability_ancestors(p_task uuid) returns table(task_id uuid)
language sql stable security definer set search_path='' as $$
 with recursive parents(id) as (select p_task union
  select r.parent_task_id from public.platform_capability_requests r join parents p on r.implementation_task_id=p.id)
 select id from parents
$$;

-- Capability implementation and incident continuations share the same original
-- reservation/call history. Traversal is bidirectional and de-duplicates nodes.
create or replace function public.platform_repair_family(p_task uuid) returns table(task_id uuid)
language sql stable security definer set search_path='' as $$
 with recursive edges(parent,child) as (
  select root_task_id,platform_task_id from public.platform_assessment_repair_attempts
  union select parent_task_id,implementation_task_id from public.platform_capability_requests
 ),related(id) as (select p_task union
  select case when e.parent=r.id then e.child else e.parent end
  from related r join edges e on e.parent=r.id or e.child=r.id)
 select id from related
$$;

create function public.platform_capability_resume() returns jsonb
language plpgsql security definer set search_path='' as $$
declare s public.platform_settings;r record;resumed jsonb='[]'::jsonb;current_source jsonb;begin
 select * into strict s from public.platform_settings where id;
 if s.paused then return resumed;end if;
 select manifest into current_source from public.platform_supervisor_activations order by created_at desc,id desc limit 1;
 for r in select p.id,q.id as request_id,q.capability_id,a.revision,a.module_sha256,
  current_source->'files'->>('capability_'||replace(q.capability_id,'-','_')||'.py')=a.module_sha256 as still_installed
  from public.platform_tasks p join public.platform_capability_requests q on q.parent_task_id=p.id
  join public.platform_capability_activations a on a.request_id=q.id
  where p.status='blocked' and p.checkpoint->'capability_wait'->>'id'=q.id::text
   and p.lease_token is null and not p.cancel_requested and p.deadline_at>clock_timestamp()
   and p.authorization_version=s.authorization_version
   and not exists(select 1 from public.platform_capability_ancestors(p.id) f join public.platform_tasks x on x.id=f.task_id where x.cancel_requested or x.status='cancelled')
   and not exists(select 1 from public.platform_repair_family(p.id) f join public.platform_tasks x on x.id=f.task_id where x.checkpoint->>'cleanup_unknown'='true')
   and not exists(select 1 from public.platform_repair_family(p.id) f join public.platform_operations o on o.task_id=f.task_id where o.status in ('pending','unknown'))
   and not exists(select 1 from public.platform_repair_family(p.id) f join public.platform_runs x on x.task_id=f.task_id where x.status='running' or x.status='unknown' and not exists(select 1 from public.platform_run_reconciliations y where y.run_id=x.id))
   and public.autonomy_budget_allows(p.budget_category,
    (select coalesce(sum(x.reserved_cents),0)::integer from public.platform_repair_family(p.id) f join public.platform_runs x on x.task_id=f.task_id),
    (select count(*)::integer from public.platform_repair_family(p.id) f join public.platform_runs x on x.task_id=f.task_id),100,1)
 loop
  update public.platform_tasks set status='implementing',
   reason=case when r.still_installed then 'Required capability verified in production; continuing original work.' else 'Capability installation changed; rebuild the missing tool under existing standing authority.' end,
   checkpoint=(checkpoint-'not_before'-'repair_guard'-'capability_wait')||jsonb_build_object('capability_activation',r.request_id),
   updated_at=clock_timestamp() where id=r.id;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),r.id,'capability-broker','capability-parent-resumed',
   'Capability availability changed; original work may continue under its unchanged counters, deadline and cancellation controls.',
   jsonb_build_object('request_id',r.request_id,'still_installed',coalesce(r.still_installed,false)));
  resumed=resumed||jsonb_build_array(r.id);
 end loop;
 return resumed;
end$$;

create function public.platform_capability_worker(p_operation text,p_worker uuid,p_task uuid,p_token uuid,p_payload jsonb default '{}')
returns jsonb language plpgsql security definer set search_path='' as $$
declare t public.platform_tasks;s public.platform_settings;r public.platform_capability_requests;
 a public.platform_capability_activations;installed public.platform_supervisor_activations;
 ident uuid;child uuid;spec jsonb;binding text;module text;flags jsonb;result jsonb;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 if jsonb_typeof(p_payload) is distinct from 'object' then raise exception 'Invalid capability operation';end if;
 select * into strict s from public.platform_settings where id;
 select * into strict t from public.platform_tasks where id=p_task for update;
 if p_worker is null or p_token is null or t.worker_id is distinct from p_worker
  or t.lease_token is distinct from p_token or t.lease_until is null or t.lease_until<=clock_timestamp()
  or t.authorization_version is distinct from s.authorization_version
 then raise exception 'Current capability worker lease required';end if;
 if p_operation='context' then
  if p_payload<>'{}'::jsonb then raise exception 'Unexpected capability context fields';end if;
  select * into r from public.platform_capability_requests where implementation_task_id=p_task;
  if not found then return null;end if;
  return jsonb_build_object('id',r.id,'parent_task_id',r.parent_task_id,'spec',r.spec,
   'artifact_id',r.artifact_id,'spec_sha256',r.spec_sha256,'requires_further_owner_approval',false);
 elsif p_operation='request' then
  if (p_payload-array['id','spec','artifact_id'])<>'{}'::jsonb then raise exception 'Unexpected capability request fields';end if;
  ident=(p_payload->>'id')::uuid;spec=p_payload->'spec';
  if ident is null or jsonb_typeof(spec) is distinct from 'object'
   or (spec-array['version','id','minimum_revision','objective','acceptance'])<>'{}'::jsonb
   or spec->>'version' is distinct from 'platform-capability-request-v1'
   or coalesce(spec->>'id','') !~ '^[a-z][a-z0-9-]{1,62}$'
   or jsonb_typeof(spec->'minimum_revision') is distinct from 'number'
   or coalesce(spec->>'minimum_revision','') !~ '^[1-9][0-9]{0,6}$'
   or (spec->>'minimum_revision')::integer>1000000
   or jsonb_typeof(spec->'objective') is distinct from 'string'
   or length(coalesce(spec->>'objective','')) not between 1 and 8000
   or jsonb_typeof(spec->'acceptance') is distinct from 'array'
   or octet_length(spec::text)>16000 then raise exception 'Invalid capability specification';end if;
  if jsonb_array_length(spec->'acceptance') not between 1 and 12
   or exists(select 1 from jsonb_array_elements(spec->'acceptance') x where jsonb_typeof(x) is distinct from 'string' or length(x#>>'{}') not between 1 and 500)
  then raise exception 'Concrete capability acceptance checks required';end if;
  binding=encode(sha256(convert_to(spec::text,'UTF8')),'hex');
  if not exists(select 1 from public.platform_artifacts x where x.id=(p_payload->>'artifact_id')::uuid
   and x.task_id=p_task and x.name='capability-request.json' and x.byte_count<=16000)
  then raise exception 'Original task-bound capability request required';end if;
  select * into r from public.platform_capability_requests where id=ident;
  if found and (r.parent_task_id,r.spec,r.artifact_id) is distinct from (p_task,spec,(p_payload->>'artifact_id')::uuid)
  then raise exception 'Capability request identity already binds other evidence';end if;
  if not found then select * into r from public.platform_capability_requests where parent_task_id=p_task and spec_sha256=binding;end if;
  if r.id is not null then
   select * into a from public.platform_capability_activations where request_id=r.id;
   if a.request_id is not null and not exists(select 1 from public.platform_supervisor_activations x
    where x.id=(select id from public.platform_supervisor_activations order by created_at desc,id desc limit 1)
    and x.manifest->'files'->>('capability_'||replace(a.capability_id,'-','_')||'.py')=a.module_sha256)
   then return jsonb_build_object('id',r.id,'available',false,'activation_lost',true,'minimum_revision',a.revision+1);end if;
   return jsonb_build_object('id',r.id,'implementation_task_id',r.implementation_task_id,'available',a.request_id is not null,'replayed',true);
  end if;
  select * into a from public.platform_capability_activations where capability_id=spec->>'id'
   and revision>=(spec->>'minimum_revision')::integer order by revision desc,created_at desc limit 1;
  if found and exists(select 1 from public.platform_supervisor_activations x
    where x.id=(select id from public.platform_supervisor_activations order by created_at desc,id desc limit 1)
    and x.manifest->'files'->>('capability_'||replace(a.capability_id,'-','_')||'.py')=a.module_sha256)
  then return jsonb_build_object('available',true,'activation_request_id',a.request_id);end if;
  flags=public.platform_worker('lease',p_worker,p_task,p_token,'{}');
  if s.paused or flags->>'cancel_requested'='true' or t.deadline_at<=clock_timestamp()+interval '180 seconds'
   or t.status in ('cancelled','completed','rolled-back','deadline','budget')
   or exists(select 1 from public.platform_capability_ancestors(p_task) f join public.platform_tasks parent on parent.id=f.task_id where parent.cancel_requested or parent.status='cancelled')
   or exists(select 1 from public.platform_repair_family(p_task) f join public.platform_tasks p on p.id=f.task_id where p.checkpoint->>'cleanup_unknown'='true')
   or exists(select 1 from public.platform_repair_family(p_task) f join public.platform_operations o on o.task_id=f.task_id where o.status in ('pending','unknown'))
   or exists(select 1 from public.platform_repair_family(p_task) f join public.platform_runs x on x.task_id=f.task_id where x.status='running' or x.status='unknown' and not exists(select 1 from public.platform_run_reconciliations y where y.run_id=x.id))
  then raise exception 'Original controls or unresolved operations prevent capability admission';end if;
  if exists(select 1 from public.platform_capability_ancestors(p_task) f join public.platform_capability_requests q on q.implementation_task_id=f.task_id where q.capability_id=p_payload->'spec'->>'id')
  then raise exception 'Capability dependency cycle; retain the implementation evidence';end if;
  if not public.autonomy_budget_allows(t.budget_category,(flags->>'committed_cents')::integer,(flags->>'model_calls')::integer,100,1)
  then raise exception 'Original category budget prevents capability implementation';end if;
  child=gen_random_uuid();
  insert into public.platform_tasks(id,requested_by,title,objective,repositories,authorization_version,budget_category,
   priority,max_reserved_cents,deadline_at,checkpoint)
  values(child,t.requested_by,left('Implement supervisor capability: '||(spec->>'id'),160),
   left('Implement and qualify the requested operational capability under existing standing authority. Read references/capabilities/index.json for the immutable specification and acceptance checks. Add a declared platform_supervisor/capability_*.py tool pack and meaningful new regression tests, then use the existing qualified supervisor self-update route. Preserve evidence, cancellation and uncertain outcomes. Never ask the owner for another grant or claim installation from a proposal. Requested functionality: '||(spec->>'objective'),12000),
   array['jumpserve-networks/jumpserve-back-end'],t.authorization_version,t.budget_category,greatest(0,t.priority-1),t.max_reserved_cents,t.deadline_at,
   jsonb_build_object('capability_request_id',ident));
  insert into public.platform_capability_requests(id,parent_task_id,implementation_task_id,capability_id,minimum_revision,spec,spec_sha256,artifact_id)
  values(ident,p_task,child,spec->>'id',(spec->>'minimum_revision')::integer,spec,binding,(p_payload->>'artifact_id')::uuid);
  result=jsonb_build_object('id',ident,'implementation_task_id',child,'available',false);
  update public.platform_tasks set status='blocked',reason='Required capability implementation queued automatically; waiting for verified production activation.',
   checkpoint=jsonb_set(checkpoint,'{capability_wait}',result),updated_at=clock_timestamp() where id=p_task;
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(ident,p_task,'capability-broker','capability-requested',
   'Missing capability became linked implementation work under standing authority; original deadlines and usage remain authoritative.',
   result||jsonb_build_object('capability_id',spec->>'id','spec_sha256',binding,'requires_further_owner_approval',false));
  return result;
 elsif p_operation='activate' then
  if (p_payload-array['request_id','module_sha256','revision','source_revision'])<>'{}'::jsonb then raise exception 'Unexpected capability activation fields';end if;
  select * into strict r from public.platform_capability_requests where id=(p_payload->>'request_id')::uuid and implementation_task_id=p_task;
  module='capability_'||replace(r.capability_id,'-','_')||'.py';
  select * into a from public.platform_capability_activations where request_id=r.id;
  if found then
   if (a.module_sha256,a.revision,a.source_revision) is distinct from (p_payload->>'module_sha256',(p_payload->>'revision')::integer,p_payload->>'source_revision') then raise exception 'Original capability activation differs';end if;
   return jsonb_build_object('available',true,'request_id',r.id,'replayed',true);
  end if;
  select * into installed from public.platform_supervisor_activations x
   where x.id=(select id from public.platform_supervisor_activations order by created_at desc,id desc limit 1)
   and x.source_revision=p_payload->>'source_revision' and x.manifest->'files'->>module=p_payload->>'module_sha256'
   and exists(select 1 from public.platform_operations o join public.platform_releases l on l.task_id=o.task_id
    where o.id=x.operation_id and o.task_id=p_task and o.status='confirmed' and o.request->>'component'='supervisor-runtime'
     and l.component='supervisor-runtime' and l.revision=x.source_revision and l.status='verified' and l.external_id=o.id::text);
  if installed.id is null or coalesce(p_payload->>'module_sha256','') !~ '^[a-f0-9]{64}$'
   or coalesce(p_payload->>'revision','') !~ '^[1-9][0-9]{0,6}$'
   or (p_payload->>'revision')::integer not between r.minimum_revision and 1000000
  then raise exception 'Verified installed capability source and original release operation required';end if;
  insert into public.platform_capability_activations(request_id,supervisor_activation_id,capability_id,revision,module_sha256,source_revision)
  values(r.id,installed.id,r.capability_id,(p_payload->>'revision')::integer,p_payload->>'module_sha256',installed.source_revision);
  -- Recording an admitted install remains possible after cancellation. Waking
  -- its parent is a separate, guarded action and never clears an unknown call.
  perform public.platform_capability_resume();
  insert into public.platform_events(id,task_id,actor,kind,message,details) values(gen_random_uuid(),r.parent_task_id,'capability-broker','capability-activated',
   'Requested capability has verified installed source; parent eligibility was evaluated without resetting original limits or claiming experiment success.',
   p_payload||jsonb_build_object('implementation_task_id',p_task,'scientific_completion',false));
  return jsonb_build_object('available',true,'request_id',r.id,'parent_resumed',exists(select 1 from public.platform_tasks where id=r.parent_task_id and status='implementing'));
 else raise exception 'Unsupported capability operation';end if;
end$$;

-- Existing incident context, closure and parent-stop paths also see capability
-- tasks linked beneath an assessment repair, without rewriting original links.
create or replace view public.platform_assessment_repair_bindings as
 with recursive bindings(blocker_id,platform_task_id,created_at) as (
  select blocker_id,platform_task_id,created_at from public.platform_assessment_repair_links
  union select blocker_id,platform_task_id,created_at from public.platform_assessment_repair_attempts
  union select b.blocker_id,r.implementation_task_id,r.created_at from bindings b
   join public.platform_capability_requests r on r.parent_task_id=b.platform_task_id)
 select blocker_id,platform_task_id,created_at from bindings;
revoke all on public.platform_assessment_repair_bindings from public,anon,authenticated,service_role;

alter function public.platform_worker(text,uuid,uuid,uuid,jsonb) rename to platform_worker_before_capabilities_v1;
revoke all on function public.platform_worker_before_capabilities_v1(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated,service_role;
create function public.platform_worker(p_operation text,p_worker uuid,p_task uuid default null,p_token uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;category text;spent integer;calls integer;related boolean;begin
 if p_operation='maintenance' then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
  if p_worker is null or not exists(select 1 from public.platform_settings s join public.platform_authorizations a on a.version=s.authorization_version
   where s.id and a.policy_sha256=p_payload->>'policy_sha256') then raise exception 'Current capability worker policy required';end if;
  perform public.platform_capability_resume();
 end if;
 if p_operation in ('claim','lease','begin-run') then
  perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
  perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
  update public.platform_tasks child set cancel_requested=true,
   status=case when child.status='queued' then 'cancelled' else child.status end
  where exists(select 1 from public.platform_capability_requests r where r.implementation_task_id=child.id)
   and not child.cancel_requested and exists(select 1 from public.platform_capability_ancestors(child.id) f
    join public.platform_tasks p on p.id=f.task_id where p.cancel_requested or p.status='cancelled');
 end if;
 related=exists(select 1 from public.platform_capability_requests where parent_task_id=p_task or implementation_task_id=p_task);
 if p_operation in ('lease','begin-run') and related then
  select budget_category into strict category from public.platform_tasks where id=p_task;
  select coalesce(sum(r.reserved_cents),0),count(*) into spent,calls from public.platform_repair_family(p_task) f join public.platform_runs r on r.task_id=f.task_id;
  if p_operation='begin-run' then
   perform public.platform_worker_before_capabilities_v1('lease',p_worker,p_task,p_token,'{}');
   if not public.autonomy_budget_allows(category,spent,calls,100,1) then return jsonb_build_object('denied','budget');end if;
  end if;
 end if;
 result=public.platform_worker_before_capabilities_v1(p_operation,p_worker,p_task,p_token,p_payload);
 if p_operation='lease' then
  result=result||jsonb_build_object('capability_contract','platform-capability-request-v1');
  if related then result=result||jsonb_build_object('committed_cents',spent,'model_calls',calls);end if;
 end if;
 return result;
end$$;
revoke all on function public.platform_capability_ancestors(uuid),public.platform_repair_family(uuid),public.platform_capability_resume() from public,anon,authenticated,service_role;
revoke all on function public.platform_capability_worker(text,uuid,uuid,uuid,jsonb),public.platform_worker(text,uuid,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.platform_capability_worker(text,uuid,uuid,uuid,jsonb),public.platform_worker(text,uuid,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
