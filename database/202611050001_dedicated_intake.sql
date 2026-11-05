begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- Disabled until the separately provisioned host and pinned warm Gateway have
-- been read back by the release operator. Heartbeats cannot enable routing.
create table public.research_intake_runtime (
 id boolean primary key default true check(id),enabled boolean not null default false,
 worker_id uuid,status text not null default 'unavailable' check(status in ('ready','unavailable','paused-auth','paused-quota')),
 seen_at timestamptz,configuration jsonb not null default '{}'
);
insert into public.research_intake_runtime(id) values(true);
alter table public.research_intake_runtime enable row level security;
revoke all on public.research_intake_runtime from public,anon,authenticated,service_role;
grant select on public.research_intake_runtime to service_role;

alter table public.research_autonomy_tasks add column intake_parent_id uuid references public.research_autonomy_tasks(id);
alter table public.research_autonomy_tasks add column intake_chunk_index integer check(intake_chunk_index>=0);
alter table public.research_autonomy_tasks add constraint intake_child_identity check(
 (intake_parent_id is null and intake_chunk_index is null) or
 (intake_parent_id is not null and intake_chunk_index is not null and claim_id is null and stage='intake' and intake_parent_id<>id));
drop index public.research_autonomy_one_intake;
create unique index research_autonomy_one_intake on public.research_autonomy_tasks(study_id) where claim_id is null and intake_parent_id is null;
create unique index research_intake_chunk_identity on public.research_autonomy_tasks(intake_parent_id,intake_chunk_index) where intake_parent_id is not null;
create function public.research_intake_identity() returns trigger language plpgsql set search_path='' as $$begin
 if (new.intake_parent_id,new.intake_chunk_index) is distinct from (old.intake_parent_id,old.intake_chunk_index)
 then raise exception 'Original intake child identity is immutable';end if;
 return new;
end$$;
create trigger research_intake_identity before update on public.research_autonomy_tasks for each row execute function public.research_intake_identity();

alter table public.research_model_dispatches add column dispatch_lane text not null default 'general' check(dispatch_lane in ('general','intake'));
-- Narrow the existing selectors rather than replacing their original budgets,
-- provider fences, authorization and cancellation checks.
do $$declare p record;body text;n integer=0;begin
 for p in select oid,pg_get_functiondef(oid) definition from pg_proc where pronamespace='public'::regnamespace and proname like 'research_model_dispatch%' loop
  if strpos(p.definition,$s$where a.status='queued'$s$)>0 then
   body=replace(p.definition,$s$where a.status='queued'$s$,$s$where a.dispatch_lane='general' and a.status='queued'$s$);execute body;n=n+1;
  end if;
 end loop;
 if n<>1 then raise exception 'Expected one original model claim selector, found %',n;end if;
 n=0;
 for p in select oid,pg_get_functiondef(oid) definition from pg_proc where pronamespace='public'::regnamespace and proname like 'research_autonomy_%' loop
  if strpos(p.definition,$s$where a.status in ('queued','waiting') and a.next_at<=clock_timestamp()$s$)>0 then
   body=replace(p.definition,$s$where a.status in ('queued','waiting') and a.next_at<=clock_timestamp()$s$,
    $s$where a.intake_parent_id is null and coalesce(a.context->>'intake_pool_version','')<>'warm-intake-v1' and not exists(select 1 from public.research_autonomy_tasks ic where ic.intake_parent_id=a.id) and (a.stage<>'intake' or not (select enabled from public.research_intake_runtime where id)) and a.status in ('queued','waiting') and a.next_at<=clock_timestamp()$s$);
   -- The dedicated controller reconciles its own expired leases. A rollback
   -- pauses chunked roots instead of handing them to an older sequential worker.
   body=replace(body,$s$where status='running' and lease_until<clock_timestamp()$s$,
    $s$where status='running' and lease_until<clock_timestamp() and not (stage='intake' and (coalesce(context->>'intake_pool_version','')='warm-intake-v1' or intake_parent_id is not null))$s$);
   execute body;n=n+1;
  end if;
 end loop;
 if n<>1 then raise exception 'Expected one original assessment lease selector, found %',n;end if;
 n=0;
 for p in select oid,pg_get_functiondef(oid) definition from pg_proc where pronamespace='public'::regnamespace and proname like 'research_autonomy_%' loop
  if strpos(p.definition,$s$if t.claim_id is null and t.status in ($s$)>0 then
   body=replace(p.definition,$s$if t.claim_id is null and t.status in ($s$,$s$if t.claim_id is null and t.intake_parent_id is null and t.status in ($s$);
   body=replace(body,$s$update public.research_paper_reviews set status=case when t.status='finished'$s$,
    $s$if t.status='finished' and exists(select 1 from public.research_autonomy_tasks child where child.intake_parent_id=t.id and child.status<>'finished') then raise exception 'Every original source chunk must finish before paper readiness';end if;
   update public.research_paper_reviews set status=case when t.status='finished'$s$);
   execute body;n=n+1;
  end if;
 end loop;
 if n<>1 then raise exception 'Expected one original paper readiness guard, found %',n;end if;
 n=0;
 for p in select oid,pg_get_functiondef(oid) definition from pg_proc where pronamespace='public'::regnamespace and proname like 'research_paper_review%' loop
  if strpos(p.definition,$s$where study_id=p_study and claim_id is null for update$s$)>0 then
   execute replace(p.definition,$s$where study_id=p_study and claim_id is null for update$s$,$s$where study_id=p_study and claim_id is null and intake_parent_id is null for update$s$);n=n+1;
  end if;
 end loop;
 if n<>1 then raise exception 'Expected one original root organization selector, found %',n;end if;
end$$;

-- Host coordination refers to the ORIGINAL shared EC2 host. Dedicated intake
-- calls and controller leases must not starve that host's repair supervisor.
do $$declare p record;body text;n integer=0;begin
 for p in select pg_get_functiondef(oid) definition from pg_proc where pronamespace='public'::regnamespace and proname like 'platform_worker%' loop
  body=p.definition;
  if strpos(body,$s$where d.status=''running'' or d.status=''queued''$s$)>0 then
   body=replace(body,$s$where d.status=''running'' or d.status=''queued''$s$,$s$where d.status=''running'' and d.dispatch_lane=''general'' or d.status=''queued'' and d.dispatch_lane=''general''$s$);
   body=replace(body,$s$public.research_model_dispatches where status in (''queued'',''running'')$s$,$s$public.research_model_dispatches where dispatch_lane=''general'' and status in (''queued'',''running'')$s$);n=n+1;
  end if;
  if strpos(body,$s$public.research_autonomy_tasks where status='running' and lease_until>clock_timestamp()$s$)>0 then
   body=replace(body,$s$public.research_autonomy_tasks where status='running' and lease_until>clock_timestamp()$s$,$s$public.research_autonomy_tasks where status='running' and lease_until>clock_timestamp() and coalesce(context->>'intake_pool_version','')<>'warm-intake-v1'$s$);n=n+1;
  end if;
  if body<>p.definition then execute body;end if;
 end loop;
 if n<>2 then raise exception 'Expected two shared-host admission guards, found %',n;end if;
 body=pg_get_functiondef('public.platform_supervisor_install(uuid,text,uuid)'::regprocedure);
 if strpos(body,$s$public.research_model_dispatches d where d.status='running'$s$)=0 or strpos(body,$s$public.research_autonomy_tasks r where r.lease_token is not null$s$)=0 then raise exception 'Expected original supervisor installation drain guards';end if;
 body=replace(body,$s$public.research_model_dispatches d where d.status='running'$s$,$s$public.research_model_dispatches d where d.dispatch_lane='general' and d.status='running'$s$);
 body=replace(body,$s$public.research_autonomy_tasks r where r.lease_token is not null$s$,$s$public.research_autonomy_tasks r where coalesce(r.context->>'intake_pool_version','')<>'warm-intake-v1' and r.lease_token is not null$s$);
 execute body;
end$$;

create function public.research_intake_control(p_operation text,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare t public.research_autonomy_tasks;w public.research_autonomy_workflows;r public.research_intake_runtime;
 c jsonb;child uuid;intake_context jsonb;finished integer;remaining integer;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict r from public.research_intake_runtime where id;
 if p_operation='health' then return jsonb_build_object('version','warm-intake-v1','enabled',r.enabled,'status',
  case when r.seen_at>clock_timestamp()-interval '30 seconds' then r.status else 'unavailable' end);end if;
 if not r.enabled or r.status<>'ready' or r.seen_at is null or r.seen_at<=clock_timestamp()-interval '30 seconds'
 then return case when p_operation='lease' then null else jsonb_build_object('blocked',true,'reason','Dedicated intake runtime is not qualified and ready.') end;end if;
 if p_operation='lease' then
  -- Reuse only completed captured answers or controller-only work. Never turn
  -- an expired/uncertain provider operation into a replacement inference.
  update public.research_autonomy_turns z set status='unknown',ended_at=clock_timestamp(),reason='Dedicated intake controller expired; original provider outcome requires reconciliation.'
   where z.status='running' and exists(select 1 from public.research_autonomy_tasks a where a.id=z.task_id and a.stage='intake' and coalesce(a.context->>'intake_pool_version','')='warm-intake-v1' and a.status='running' and a.lease_until<=clock_timestamp());
  update public.research_autonomy_tasks a set status=case when
   exists(select 1 from public.research_autonomy_turns z where z.task_id=a.id and z.status in ('running','unknown','failed'))
   or exists(select 1 from public.research_model_dispatches d where d.task_id=a.id and d.status in ('queued','running','unknown'))
   then 'blocked' else 'queued' end,
   reason='Expired intake controller reconciled; captured complete answers are reused, uncertain calls remain fenced.',
   lease_token=null,lease_until=null,next_at=clock_timestamp(),updated_at=clock_timestamp()
   where a.stage='intake' and coalesce(a.context->>'intake_pool_version','')='warm-intake-v1' and a.status='running' and a.lease_until<=clock_timestamp();
  if (select count(*) from public.research_autonomy_tasks a join public.research_autonomy_workflows b on b.study_id=a.study_id where a.stage='intake' and a.status='running' and a.lease_until>clock_timestamp() and b.status='running')>=4 then return null;end if;
  select a.* into t from public.research_autonomy_tasks a join public.research_autonomy_workflows b on b.study_id=a.study_id
   where a.stage='intake' and a.status in ('queued','waiting') and a.next_at<=clock_timestamp()
    and b.status='running' and b.deadline_at>clock_timestamp()+interval '420 seconds'
    and (b.max_spend_cents is null or b.committed_cents+5<=b.max_spend_cents)
    and (select count(*) from public.research_autonomy_tasks x where x.study_id=a.study_id and x.status='running' and x.lease_until>clock_timestamp())<2
    and (a.intake_parent_id is not null or not exists(select 1 from public.research_autonomy_tasks x where x.intake_parent_id=a.id and x.status in ('queued','waiting','running')))
    and public.autonomy_budget_allows('research_assessment',b.committed_cents,(select count(*)::integer from public.research_autonomy_turns z where z.study_id=b.study_id),5,0)
   order by (a.intake_parent_id is null),a.next_at,a.created_at,a.id for update of a skip locked limit 1;
  if not found then return null;end if;
  update public.research_autonomy_tasks set status='running',lease_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '420 seconds',context=context||jsonb_build_object('intake_pool_version','warm-intake-v1'),updated_at=clock_timestamp() where id=t.id returning * into t;
  update public.research_autonomy_workflows set committed_cents=committed_cents+5,updated_at=clock_timestamp() where study_id=t.study_id returning * into w;
  insert into public.research_autonomy_events(study_id,task_id,event,details) values(t.study_id,t.id,'intake-controller-slot',jsonb_build_object('version','warm-intake-v1','reserved_cents',5));
  return to_jsonb(t)||jsonb_build_object('intake_pool',true,'workflow',to_jsonb(w),'actor_id',(select owner_id from public.research_study_owners where study_id=t.study_id));
 elsif p_operation='chunks' then
  select * into strict t from public.research_autonomy_tasks where id=(p_payload->>'task_id')::uuid for update;
  select * into strict w from public.research_autonomy_workflows where study_id=t.study_id;
  if t.stage<>'intake' or t.intake_parent_id is not null or t.status<>'running' or t.lease_token is distinct from (p_payload->>'token')::uuid
   or t.lease_until<=clock_timestamp() or w.status<>'running' or w.deadline_at<=clock_timestamp()
   then raise exception 'Current original intake lease required';end if;
  -- A new child identity must never bypass an uncertain ORIGINAL parent call.
  if exists(select 1 from public.research_model_dispatches d where d.task_id=t.id and
   (d.status in ('queued','running') or d.status='unknown' and not exists(select 1 from public.research_model_reconciliations x where x.dispatch_id=d.id and x.request_sha256=d.request_sha256)))
   or exists(select 1 from public.research_autonomy_turns z where z.task_id=t.id and z.status in ('running','unknown'))
   then return jsonb_build_object('blocked',true,'reason','Original intake invocation remains unconfirmed; parallel child identities cannot replace it.');end if;
  if jsonb_typeof(p_payload->'chunks') is distinct from 'array' or jsonb_array_length(p_payload->'chunks') not between 1 and 512 then raise exception 'Bounded complete chunk manifest required';end if;
  if (select count(distinct value->>'index') from jsonb_array_elements(p_payload->'chunks'))<>jsonb_array_length(p_payload->'chunks') then raise exception 'Unique source chunk indices required';end if;
  for c in select value from jsonb_array_elements(p_payload->'chunks') loop
   if jsonb_typeof(c) is distinct from 'object' or not c ?& array['index','sha256'] or c-array['index','sha256']<>'{}'::jsonb
    or jsonb_typeof(c->'index') is distinct from 'number' or c->>'index' !~ '^[0-9]{1,6}$'
    or (c->>'index')::integer<coalesce((t.context->>'chunk_index')::integer,0)
    or jsonb_typeof(c->'sha256') is distinct from 'string' or c->>'sha256' !~ '^[a-f0-9]{64}$' then raise exception 'Original unprocessed chunk identity required';end if;
   -- Stable across admission acknowledgements, controller retries and restarts.
   child=md5(t.id::text||':intake-chunk:'||(c->>'index'))::uuid;
   intake_context=(t.context-'review_selection'-'parallel_intake')||jsonb_build_object('intake_chunk_sha256',c->>'sha256');
   insert into public.research_autonomy_tasks(id,study_id,stage,context,intake_parent_id,intake_chunk_index,reason)
    values(child,t.study_id,'intake',intake_context,t.id,(c->>'index')::integer,'Independent source chunk queued; original quote/page validation is required.') on conflict(id) do nothing;
   if not exists(select 1 from public.research_autonomy_tasks x where x.id=child and x.study_id=t.study_id and x.intake_parent_id=t.id and x.intake_chunk_index=(c->>'index')::integer
    and x.context->>'intake_chunk_sha256'=c->>'sha256' and x.context->>'source_id'=t.context->>'source_id' and x.context->>'text_artifact_id'=t.context->>'text_artifact_id') then raise exception 'Retained chunk manifest differs';end if;
  end loop;
  if exists(select 1 from public.research_autonomy_tasks where intake_parent_id=t.id and status in ('blocked','budget','deadline','attempt-limit','cancelled')) then
   return jsonb_build_object('blocked',true,'reason','A source chunk has a recorded blocker; successful sibling evidence is retained and no missing chunk is claimed complete.');end if;
  select count(*) filter(where status='finished'),count(*) filter(where status<>'finished') into finished,remaining from public.research_autonomy_tasks where intake_parent_id=t.id;
  return jsonb_build_object('complete',finished,'remaining',remaining);
 end if;
 raise exception 'Unsupported intake controller operation';
end$$;

create function public.research_intake_dispatch(p_operation text,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.research_model_dispatches;t public.research_autonomy_tasks;r public.research_intake_runtime;result jsonb;begin
 perform pg_advisory_xact_lock(hashtextextended('research-intake-dispatch-v1',0));
 select * into strict r from public.research_intake_runtime where id;
 if p_operation='heartbeat' then
  if p_payload->>'version' is distinct from 'warm-intake-v1' or p_payload->'configuration'->>'native_version' is distinct from '2026.10.5'
   or p_payload->'configuration'->>'gateway_verified' is distinct from 'true' then raise exception 'Pinned warm native Gateway proof required';end if;
  update public.research_intake_runtime set worker_id=(p_payload->>'worker_id')::uuid,status=p_payload->>'status',seen_at=clock_timestamp(),configuration=p_payload->'configuration' where id;
  return jsonb_build_object('retained',true);
 elsif p_operation='enqueue' then
  select * into strict t from public.research_autonomy_tasks where id=(p_payload->>'task_id')::uuid;
  if not r.enabled or t.stage<>'intake' then raise exception 'Dedicated intake admission is not active';end if;
  select * into d from public.research_model_dispatches where id=(p_payload->>'id')::uuid;
  if found and d.dispatch_lane<>'intake' then raise exception 'Original general dispatch cannot change lanes';end if;
  result=public.research_model_dispatch(p_operation,p_payload);
  update public.research_model_dispatches set dispatch_lane='intake' where id=(result->>'id')::uuid and status='queued';
  return result;
 elsif p_operation='claim' then
  if not r.enabled or r.status<>'ready' or r.seen_at<=clock_timestamp()-interval '30 seconds' then return null;end if;
  update public.research_model_dispatches set status='unknown',ended_at=clock_timestamp(),provenance=provenance||jsonb_build_object('reason','Dedicated intake worker lease expired; original call requires reconciliation.')
   where dispatch_lane='intake' and status='running' and lease_until<=clock_timestamp();
  if (select count(*) from public.research_model_dispatches where dispatch_lane='intake' and status='running')>=2 then return null;end if;
  select a.* into d from public.research_model_dispatches a join public.research_autonomy_turns z on z.id=a.id
   join public.research_autonomy_tasks q on q.id=a.task_id join public.research_autonomy_workflows w on w.study_id=a.study_id
   where a.dispatch_lane='intake' and a.status='queued' and z.status='running' and q.stage='intake' and q.status='running'
    and q.lease_until>clock_timestamp()+interval '240 seconds' and w.status='running' and w.deadline_at>clock_timestamp()+interval '240 seconds'
    and (w.max_spend_cents is null or w.committed_cents<=w.max_spend_cents)
    and public.autonomy_budget_allows('research_assessment',w.committed_cents,(select count(*)::integer from public.research_autonomy_turns x where x.study_id=w.study_id),0,0)
   order by a.created_at,a.id for update of a skip locked limit 1;
  if not found then return null;end if;
  update public.research_model_dispatches set status='running',lease_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '235 seconds' where id=d.id returning * into d;
  return to_jsonb(d)||jsonb_build_object('actor_id',(select owner_id from public.research_study_owners where study_id=d.study_id));
 elsif p_operation in ('result','finish') then
  if not exists(select 1 from public.research_model_dispatches where id=(p_payload->>'id')::uuid and dispatch_lane='intake') then raise exception 'Original intake dispatch required';end if;
  return public.research_model_dispatch(p_operation,p_payload);
 end if;
 raise exception 'Unsupported intake dispatch operation';
end$$;
revoke all on function public.research_intake_identity() from public,anon,authenticated,service_role;
revoke all on function public.research_intake_control(text,jsonb),public.research_intake_dispatch(text,jsonb) from public,anon,authenticated;
grant execute on function public.research_intake_control(text,jsonb),public.research_intake_dispatch(text,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
