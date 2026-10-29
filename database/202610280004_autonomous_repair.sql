begin;

create table public.research_autonomy_repairs (
 id uuid primary key, study_id uuid not null, task_id uuid not null,
 version text not null check(version='autonomous-repair-v1'),
 category text not null check(category in ('runtime','reference','implementation')),
 original_stage text not null, incident_raw text not null check(octet_length(incident_raw)<=300000),
 incident_sha256 text not null check(incident_sha256=encode(sha256(convert_to(incident_raw,'UTF8')),'hex')),
 original_context jsonb not null, state text not null check(state in ('diagnosing','repairing','validating','resuming','waiting','resolved','blocked','budget','deadline','cancelled')),
 revision integer not null default 0 check(revision>=0), evidence jsonb not null default '{}',
 reason text not null, created_at timestamptz not null default clock_timestamp(), updated_at timestamptz not null default clock_timestamp(),
 foreign key(study_id,task_id) references public.research_autonomy_tasks(study_id,id),
 unique(task_id,incident_sha256)
);
create unique index research_one_active_repair on public.research_autonomy_repairs(task_id)
 where state in ('diagnosing','repairing','validating','resuming','waiting');
create table public.research_autonomy_repair_events (
 id uuid primary key default gen_random_uuid(), repair_id uuid not null references public.research_autonomy_repairs(id),
 study_id uuid not null references public.research_studies(id), task_id uuid not null,
 revision integer not null, state text not null, details jsonb not null,
 created_at timestamptz not null default clock_timestamp(), unique(repair_id,revision)
);
create function public.research_repair_immutable() returns trigger language plpgsql set search_path='' as $$ begin
 if tg_op='DELETE' or tg_table_name='research_autonomy_repair_events' then raise exception 'Repair history is append-only';end if;
 if (new.id,new.study_id,new.task_id,new.version,new.category,new.original_stage,new.incident_raw,new.incident_sha256,new.original_context,new.created_at)
  is distinct from (old.id,old.study_id,old.task_id,old.version,old.category,old.original_stage,old.incident_raw,old.incident_sha256,old.original_context,old.created_at)
  or old.state in ('resolved','blocked','budget','deadline','cancelled') or new.revision<>old.revision+1
 then raise exception 'Original repair identity/snapshot and terminal outcomes are immutable';end if;
 return new;
end $$;
create trigger repair_originals before update or delete on public.research_autonomy_repairs for each row execute function public.research_repair_immutable();
create trigger repair_events_immutable before update or delete on public.research_autonomy_repair_events for each row execute function public.research_repair_immutable();

-- Repairs use the original claim's ordinary controller lease and model admission.
-- This RPC does not mint provider tokens, extend a deadline, refund commitments,
-- alter scientific findings or launch/replace an experiment.
create function public.research_autonomy_repair(p_operation text,p_study uuid,p_task uuid,p_token uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare t public.research_autonomy_tasks; w public.research_autonomy_workflows; r public.research_autonomy_repairs;
 progress jsonb; ctx jsonb; target text; denied text;
begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into strict w from public.research_autonomy_workflows where study_id=p_study for update;
 select * into strict t from public.research_autonomy_tasks where study_id=p_study and id=p_task for update;
 if t.claim_id is null then raise exception 'A repair requires a retained claim';end if;
 if p_operation='adopt' then
  if t.status<>'blocked' or w.status not in ('running','completed-with-blockers') then return jsonb_build_object('denied','state');end if;
 elsif t.status<>'running' or t.lease_token is null or p_token is null or t.lease_token is distinct from p_token or t.lease_until is null or t.lease_until<=clock_timestamp() then
  raise exception 'Current original task lease required';
 end if;
 denied=case when w.status in ('budget','deadline','cancelled') then w.status when w.deadline_at<=clock_timestamp()+interval '180 seconds' then 'deadline' when w.committed_cents>=w.max_spend_cents then 'budget' end;
 if denied is not null and not (p_operation='transition' and p_payload->>'state' in ('budget','deadline','cancelled')) then return jsonb_build_object('denied',denied);end if;
 if p_operation in ('enqueue','adopt') then
  if p_payload->>'version'<>'autonomous-repair-v1' or p_payload->>'category' not in ('runtime','reference','implementation')
    or p_payload->>'original_stage'<>t.stage or p_payload->'original_context' is distinct from t.context
    or jsonb_typeof(p_payload->'context')<>'object' or octet_length((p_payload->'context')::text)>240000 then raise exception 'Exact repair version/stage/context required';end if;
  select * into r from public.research_autonomy_repairs where task_id=t.id and state in ('diagnosing','repairing','validating','resuming','waiting') for update;
  if not found then
   select * into r from public.research_autonomy_repairs where task_id=t.id and incident_sha256=p_payload->>'incident_sha256';
   if found then return jsonb_build_object('denied','retained-incident','repair',to_jsonb(r));end if;
   insert into public.research_autonomy_repairs(id,study_id,task_id,version,category,original_stage,incident_raw,incident_sha256,original_context,state,reason)
    values((p_payload->>'id')::uuid,p_study,p_task,'autonomous-repair-v1',p_payload->>'category',t.stage,p_payload->>'incident_raw',p_payload->>'incident_sha256',t.context,'diagnosing',p_payload->>'reason') returning * into r;
   insert into public.research_autonomy_repair_events(repair_id,study_id,task_id,revision,state,details)
    values(r.id,p_study,p_task,0,r.state,jsonb_build_object('incident_sha256',r.incident_sha256,'original_stage',t.stage,'reason',r.reason));
  end if;
  progress=jsonb_build_object('version',r.version,'id',r.id,'state',r.state,'category',r.category,'revision',r.revision,'updated_at',r.updated_at);
  ctx=(p_payload->'context')||jsonb_build_object('repair_progress',progress);
  update public.research_autonomy_tasks set status='queued',context=ctx,reason='Autonomous repair: diagnosing the recorded failure; prior evidence and limits retained.',lease_token=null,lease_until=null,next_at=clock_timestamp(),updated_at=clock_timestamp() where id=t.id returning * into t;
  update public.research_autonomy_workflows set status='running',updated_at=clock_timestamp() where study_id=p_study;
  return jsonb_build_object('task',to_jsonb(t),'repair',to_jsonb(r));
 elsif p_operation='transition' then
  select * into strict r from public.research_autonomy_repairs where id=(p_payload->>'id')::uuid and task_id=t.id and study_id=p_study for update;
  if r.revision is distinct from (p_payload->>'expected_revision')::integer then raise exception 'Stale repair revision';end if;
  target=p_payload->>'state';
  if not ((r.state='diagnosing' and target in ('diagnosing','waiting','repairing','validating','blocked'))
   or (r.state='waiting' and target in ('waiting','diagnosing','blocked'))
   or (r.state='repairing' and target in ('repairing','diagnosing','validating','waiting','blocked'))
   or (r.state='validating' and target in ('resuming','diagnosing','blocked'))
   or (r.state='resuming' and target in ('resolved','diagnosing','blocked')) or (r.state in ('diagnosing','repairing','validating','resuming','waiting') and target in ('budget','deadline','cancelled'))) then raise exception 'Invalid repair transition';end if;
  if target in ('validating','resuming','resolved') and p_payload->'evidence' is null then raise exception 'Recorded validation evidence required';end if;
  if target in ('resuming','resolved') and ((p_payload->'evidence'->>'validated') is distinct from 'true'
   or exists(select 1 from public.research_autonomy_turns where task_id=t.id and status='running')
   or exists(select 1 from public.research_builder_calls where task_id=t.id and status in ('running','unknown'))
   or exists(select 1 from public.research_model_dispatches where task_id=t.id and status in ('queued','running')))
   then raise exception 'Validated correction and quiescent original identities required';end if;
  update public.research_autonomy_repairs set state=target,revision=revision+1,evidence=p_payload->'evidence',reason=p_payload->>'reason',updated_at=clock_timestamp() where id=r.id returning * into r;
  insert into public.research_autonomy_repair_events(repair_id,study_id,task_id,revision,state,details)
   values(r.id,p_study,p_task,r.revision,r.state,jsonb_build_object('reason',r.reason,'evidence',r.evidence));
  return to_jsonb(r);
 end if;
 raise exception 'Unsupported repair operation';
end $$;

create function public.research_autonomy_repair_candidates() returns jsonb language sql security definer set search_path='' as $$
 select coalesce(jsonb_agg(to_jsonb(t)),'[]') from (
  select a.* from public.research_autonomy_tasks a join public.research_autonomy_workflows w on w.study_id=a.study_id
  where a.status='blocked' and a.claim_id is not null and w.status in ('running','completed-with-blockers')
   and w.committed_cents<w.max_spend_cents and w.deadline_at>clock_timestamp()+interval '480 seconds'
   and not (a.context ? 'repair_progress')
  order by a.updated_at limit 8
 )t
$$;

alter table public.research_autonomy_repairs enable row level security;
alter table public.research_autonomy_repair_events enable row level security;
revoke all on public.research_autonomy_repairs,public.research_autonomy_repair_events from public,anon,authenticated;
grant select,insert,update on public.research_autonomy_repairs to service_role;
grant select,insert on public.research_autonomy_repair_events to service_role;
revoke all on function public.research_autonomy_repair(text,uuid,uuid,uuid,jsonb),public.research_autonomy_repair_candidates(),public.research_repair_immutable() from public,anon,authenticated;
grant execute on function public.research_autonomy_repair(text,uuid,uuid,uuid,jsonb),public.research_autonomy_repair_candidates() to service_role;
notify pgrst,'reload schema';
commit;
