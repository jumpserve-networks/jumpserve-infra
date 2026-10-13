begin;

-- Operational state is private and mutable only through server RPCs. Scientific
-- evidence, job definitions and event history remain immutable.
create table public.research_queue_jobs (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 campaign_id uuid not null, input_artifact_id uuid, followup_of uuid,
 execution_mode text not null check(execution_mode in ('automatic','manual')),
 priority integer not null check(priority between 1 and 5),
 dependencies jsonb not null check(jsonb_typeof(dependencies)='array' and jsonb_array_length(dependencies)<=32),
 exclusive_resources text[] not null check(cardinality(exclusive_resources)<=16),
 request jsonb not null, definition_sha256 text not null check(definition_sha256 ~ '^[a-f0-9]{64}$'),
 status text not null check(status in ('queued','manual','running','awaiting-review','reviewed','failed','cancelled','expired')),
 reason text not null, run_id uuid, lease_token uuid, lease_until timestamptz,
 created_at timestamptz not null default clock_timestamp(), updated_at timestamptz not null default clock_timestamp(),
 unique(study_id,id),
 foreign key(study_id,campaign_id) references public.research_campaigns(study_id,id),
 foreign key(study_id,input_artifact_id) references public.research_artifacts(study_id,id),
 foreign key(study_id,run_id) references public.research_runs(study_id,id),
 foreign key(study_id,followup_of) references public.research_queue_jobs(study_id,id),
 check(execution_mode<>'automatic' or input_artifact_id is not null),
 check((status='running' and lease_token is not null and lease_until is not null) or
       (status<>'running' and lease_token is null and lease_until is null))
);
create table public.research_queue_events (
 id uuid primary key, study_id uuid not null, job_id uuid not null,
 event text not null, status text not null, reason text not null, details jsonb not null,
 created_at timestamptz not null default clock_timestamp(),
 foreign key(study_id,job_id) references public.research_queue_jobs(study_id,id)
);
create function public.research_queue_definition_immutable() returns trigger
language plpgsql set search_path='' as $$ begin
 if tg_op='DELETE' or (to_jsonb(new)-array['status','reason','run_id','lease_token','lease_until','updated_at'])
  is distinct from (to_jsonb(old)-array['status','reason','run_id','lease_token','lease_until','updated_at']) then
  raise exception 'Queue definitions are immutable; create a new follow-up job';
 end if;
 return new;
end $$;
create trigger research_queue_definition_immutable before update or delete on public.research_queue_jobs
 for each row execute function public.research_queue_definition_immutable();
create trigger research_queue_event_immutable before update or delete on public.research_queue_events
 for each row execute function public.research_immutable();
do $$ declare t text; begin
 foreach t in array array['research_queue_jobs','research_queue_events'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated',t);
  execute format('grant all on public.%I to service_role',t);
 end loop;
end $$;
create index research_queue_ready on public.research_queue_jobs(priority,created_at,id) where status='queued';
create index research_queue_study on public.research_queue_jobs(study_id,created_at,id);
create index research_queue_history on public.research_queue_events(study_id,job_id,created_at,id);

create function public.research_queue_enqueue(p_study uuid,p_actor uuid,p_id uuid,p_request jsonb,p_sha256 text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare prior public.research_queue_jobs; c public.research_campaigns; p public.research_protocols;
 a public.research_artifacts; d jsonb; resources text[]; mode text; begin
 perform pg_advisory_xact_lock(hashtextextended('research-queue-v1',0));
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0));
 if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Study not found'; end if;
 select * into prior from public.research_queue_jobs where id=p_id;
 if found then
  if prior.study_id<>p_study or prior.request is distinct from p_request or prior.definition_sha256<>p_sha256 then raise exception 'Queue ID already used for another definition'; end if;
  return to_jsonb(prior)-'lease_token';
 end if;
 if (select count(*) from public.research_queue_jobs where study_id=p_study)>=1000 then raise exception 'Study queue budget exhausted'; end if;
 select * into c from public.research_campaigns where study_id=p_study and id=(p_request->>'campaign_id')::uuid;
 if c.id is null then raise exception 'Campaign not found'; end if;
 select * into p from public.research_protocols where study_id=p_study and id=c.protocol_id;
 if p.id is null then raise exception 'Frozen protocol required'; end if;
 if not exists(select 1 from public.research_claim_checks where study_id=p_study and campaign_id=c.id and applicability='applicable') then raise exception 'An applicable claim check is required'; end if;
 mode=p_request->>'execution_mode';
 if mode not in ('automatic','manual') then raise exception 'Unknown execution mode'; end if;
 if jsonb_typeof(p_request->'dependencies') is distinct from 'array' or jsonb_array_length(p_request->'dependencies')>32 then raise exception 'Invalid dependencies'; end if;
 if (select count(distinct value->>'job_id') from jsonb_array_elements(p_request->'dependencies'))<>jsonb_array_length(p_request->'dependencies') then raise exception 'Duplicate dependencies'; end if;
 for d in select value from jsonb_array_elements(p_request->'dependencies') loop
  if d->>'requirement' not in ('complete-run','reviewed-evidence') or d->>'requirement' is null then raise exception 'Dependency criterion required'; end if;
  if not exists(select 1 from public.research_queue_jobs where study_id=p_study and id=(d->>'job_id')::uuid) then raise exception 'Dependencies must be existing jobs in this study'; end if;
 end loop;
 if p_request->>'followup_of' is not null and not exists(select 1 from public.research_queue_jobs where study_id=p_study and id=(p_request->>'followup_of')::uuid) then raise exception 'Follow-up predecessor not found'; end if;
 if length(coalesce(p_request->>'rationale','')) not between 1 and 5000 then raise exception 'Job rationale required'; end if;
 if jsonb_typeof(p_request->'exclusive_resources') is distinct from 'array' then raise exception 'Resources must be an array'; end if;
 select coalesce(array_agg(value),'{}'::text[]) into resources from jsonb_array_elements_text(p_request->'exclusive_resources');
 if cardinality(resources)>16 or exists(select 1 from unnest(resources) r where r !~ '^[a-z0-9][a-z0-9:._/-]{0,99}$') then raise exception 'Invalid exclusive resource identity'; end if;
 if mode='automatic' then
  if c.adapter<>'matched-numeric-v1' or c.experiment_type not in ('reanalysis','independent-check') then raise exception 'Campaign requires a domain implementation or manual review'; end if;
  if (p.document->'resource_limits'->>'max_observations')::integer>1000 or (p.document->'resource_limits'->>'wall_seconds')::integer>10 then raise exception 'Protocol exceeds queue execution limits'; end if;
  select * into a from public.research_artifacts where study_id=p_study and id=(p_request->>'input_artifact_id')::uuid;
  if a.id is null or a.byte_count>256000 or a.byte_count>(p.document->'resource_limits'->>'max_input_bytes')::bigint or
   not exists(select 1 from jsonb_array_elements(p.document->'input_versions') v where v->>'sha256'=a.sha256) then raise exception 'Exact frozen input artifact required'; end if;
 end if;
 insert into public.research_queue_jobs(id,study_id,campaign_id,input_artifact_id,followup_of,execution_mode,priority,dependencies,exclusive_resources,request,definition_sha256,status,reason)
 values(p_id,p_study,c.id,(p_request->>'input_artifact_id')::uuid,(p_request->>'followup_of')::uuid,mode,(p_request->>'priority')::integer,p_request->'dependencies',resources,p_request,p_sha256,
  case when mode='manual' then 'manual' else 'queued' end,case when mode='manual' then 'Requires a domain operator or substantive source review; no automatic experiment available.' else 'Waiting for prerequisites and a bounded worker slot.' end)
 returning * into prior;
 insert into public.research_queue_events values(gen_random_uuid(),p_study,p_id,'enqueued',prior.status,prior.reason,jsonb_build_object('definition_sha256',p_sha256,'actor_id',p_actor),default);
 return to_jsonb(prior)-'lease_token';
end $$;

-- This serializes only short scheduling transactions; experiments run outside
-- the transaction concurrently. A global lock also makes resource caps atomic.
create function public.research_queue_claim(p_worker uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare j public.research_queue_jobs; expired public.research_queue_jobs; begin
 perform pg_advisory_xact_lock(hashtextextended('research-queue-v1',0));
 for expired in update public.research_queue_jobs set status='expired',reason='Worker lease expired; execution/storage outcome is uncertain. No automatic retry.',lease_token=null,lease_until=null,updated_at=clock_timestamp()
  where status='running' and lease_until<=clock_timestamp() returning * loop
  insert into public.research_queue_events values(gen_random_uuid(),expired.study_id,expired.id,'lease-expired','expired',expired.reason,'{"actual_usage":null}'::jsonb,default);
 end loop;
 if (select count(*) from public.research_queue_jobs where status='running')>=4 then return null; end if;
 for j in select q.* from public.research_queue_jobs q where q.status='queued' and q.execution_mode='automatic'
  and (select count(*) from public.research_queue_jobs active where active.study_id=q.study_id and active.status='running')<2
  and not exists(select 1 from public.research_queue_jobs active where active.status='running' and active.exclusive_resources && q.exclusive_resources)
  and not exists(select 1 from jsonb_array_elements(q.dependencies) d
    join public.research_queue_jobs previous on previous.id=(d->>'job_id')::uuid and previous.study_id=q.study_id
    left join public.research_runs r on r.id=previous.run_id and r.study_id=q.study_id
    where (d->>'requirement'='complete-run' and (previous.status not in ('awaiting-review','reviewed') or r.status is distinct from 'complete'))
       or (d->>'requirement'='reviewed-evidence' and previous.status<>'reviewed'))
  order by q.priority,q.created_at,q.id for update skip locked loop
  update public.research_queue_jobs set status='running',reason='Bounded worker executing the frozen campaign.',lease_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '600 seconds',updated_at=clock_timestamp() where id=j.id returning * into j;
  insert into public.research_queue_events values(gen_random_uuid(),j.study_id,j.id,'claimed','running',j.reason,jsonb_build_object('worker_id',p_worker,'lease_until',j.lease_until,'global_slots',4,'study_slots',2),default);
  return to_jsonb(j);
 end loop;
 return null;
end $$;

create function public.research_queue_finish(p_job uuid,p_token uuid,p_records jsonb,p_run uuid,p_error text,p_usage jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare j public.research_queue_jobs; owner_id uuid; r public.research_runs; begin
 perform pg_advisory_xact_lock(hashtextextended('research-queue-v1',0));
 select * into j from public.research_queue_jobs where id=p_job for update;
 if j.id is null or j.status<>'running' or j.lease_token is distinct from p_token or j.lease_until<=clock_timestamp() then raise exception 'Worker lease is stale; completion refused'; end if;
 select o.owner_id into owner_id from public.research_study_owners o where o.study_id=j.study_id;
 if p_run is not null then
  if p_run<>j.id then raise exception 'Queue run identity differs'; end if;
  -- Only this job's run is allowed; shared source evidence is read, not rewritten.
  if exists(select 1 from jsonb_array_elements(p_records) e where e->>'kind' not in ('artifacts','runs','published_values','measurements','summaries')) or
   (select count(*) from jsonb_array_elements(p_records) e where e->>'kind'='runs')<>1 or
   exists(select 1 from jsonb_array_elements(p_records) e where (e->>'kind'='runs' and (e->'record'->>'id'<>p_run::text or e->'record'->>'campaign_id'<>j.campaign_id::text)) or
    (e->>'kind' in ('measurements','summaries') and e->'record'->>'run_id'<>p_run::text)) then raise exception 'Invalid queue evidence bundle'; end if;
  perform public.research_append_bundle(j.study_id,owner_id,p_records);
  select * into r from public.research_runs where study_id=j.study_id and id=p_run and campaign_id=j.campaign_id;
  if r.id is null then raise exception 'Recorded run required'; end if;
 end if;
 update public.research_queue_jobs set status=case when r.status in ('complete','partial') then 'awaiting-review' else 'failed' end,
  reason=case when r.status in ('complete','partial') then 'Evidence recorded; claim-specific assessment and review are pending.' else coalesce(p_error,r.reason,'Worker failed before a run could be recorded; usage is unavailable.') end,
  run_id=p_run,lease_token=null,lease_until=null,updated_at=clock_timestamp() where id=p_job returning * into j;
 insert into public.research_queue_events values(gen_random_uuid(),j.study_id,j.id,'finished',j.status,j.reason,jsonb_build_object('run_id',p_run,'run_status',r.status,'usage',p_usage),default);
 return to_jsonb(j)-'lease_token';
end $$;

create function public.research_queue_action(p_study uuid,p_actor uuid,p_job uuid,p_id uuid,p_action text,p_reason text,p_assessments jsonb,p_run uuid default null)
returns jsonb language plpgsql security definer set search_path='' as $$
declare j public.research_queue_jobs; prior public.research_queue_events; item uuid; definition jsonb; begin
 perform pg_advisory_xact_lock(hashtextextended('research-queue-v1',0));
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0));
 if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Study not found'; end if;
 if p_action not in ('cancel','review','attach-run') or length(coalesce(p_reason,'')) not between 1 and 5000 then raise exception 'Action and reason required'; end if;
 definition=jsonb_build_object('actor_id',p_actor,'assessment_ids',p_assessments,'run_id',p_run);
 select * into prior from public.research_queue_events where id=p_id;
 if found then
  if prior.study_id<>p_study or prior.job_id<>p_job or prior.event<>p_action or prior.reason<>p_reason or prior.details is distinct from definition then raise exception 'Action ID already used for another request'; end if;
  return jsonb_build_object('replayed',true,'event',to_jsonb(prior)-'details');
 end if;
 select * into j from public.research_queue_jobs where id=p_job and study_id=p_study for update;
 if j.id is null then raise exception 'Job not found'; end if;
 if p_action='cancel' then
  if j.status not in ('queued','manual') then raise exception 'Only unstarted jobs may be cancelled'; end if;
  update public.research_queue_jobs set status='cancelled',reason=p_reason,updated_at=clock_timestamp() where id=p_job returning * into j;
 elsif p_action='attach-run' then
  if j.status<>'manual' then raise exception 'Only manual tasks accept externally recorded runs'; end if;
  if not exists(select 1 from public.research_runs where study_id=p_study and campaign_id=j.campaign_id and id=p_run) then raise exception 'A recorded domain run in this campaign is required'; end if;
  if exists(select 1 from jsonb_array_elements(j.dependencies) d
   join public.research_queue_jobs previous on previous.study_id=p_study and previous.id=(d->>'job_id')::uuid
   left join public.research_runs r on r.study_id=p_study and r.id=previous.run_id
   where (d->>'requirement'='reviewed-evidence' and previous.status<>'reviewed') or
    (d->>'requirement'='complete-run' and (previous.status not in ('awaiting-review','reviewed') or r.status is distinct from 'complete'))) then raise exception 'Manual task prerequisites are unmet'; end if;
  update public.research_queue_jobs set status=case when (select status from public.research_runs where id=p_run) in ('complete','partial') then 'awaiting-review' else 'failed' end,
   reason=p_reason,run_id=p_run,updated_at=clock_timestamp() where id=p_job returning * into j;
 else
  if j.status<>'awaiting-review' or j.run_id is null then raise exception 'Recorded evidence awaiting review required'; end if;
  if jsonb_typeof(p_assessments) is distinct from 'array' or jsonb_array_length(p_assessments)=0 then raise exception 'Claim assessments required'; end if;
  if exists(select 1 from jsonb_array_elements_text(p_assessments) i where not exists(select 1 from public.research_assessments a where a.id=i::uuid and a.study_id=p_study and a.campaign_id=j.campaign_id and a.evidence @> jsonb_build_array(jsonb_build_object('kind','runs','id',j.run_id)))) then raise exception 'Assessments must cite this run and campaign'; end if;
  if exists(select 1 from public.research_claim_checks c where c.study_id=p_study and c.campaign_id=j.campaign_id and c.applicability='applicable' and not exists(select 1 from public.research_assessments a where a.study_id=p_study and a.claim_id=c.claim_id and a.id::text in (select jsonb_array_elements_text(p_assessments)))) then raise exception 'Every linked applicable claim needs an assessment'; end if;
  update public.research_queue_jobs set status='reviewed',reason=p_reason,updated_at=clock_timestamp() where id=p_job returning * into j;
 end if;
 insert into public.research_queue_events values(p_id,p_study,p_job,p_action,j.status,p_reason,definition,default);
 return to_jsonb(j)-'lease_token';
end $$;

create function public.research_queue_snapshot(p_study uuid,p_actor uuid)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare jobs jsonb; events jsonb; begin
 if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Study not found'; end if;
 if (select count(*) from public.research_queue_jobs where study_id=p_study)>1000 or
    (select count(*) from public.research_queue_events where study_id=p_study)>5000 then raise exception 'Queue export budget exceeded'; end if;
 select coalesce(jsonb_agg((to_jsonb(q)-'lease_token')||jsonb_build_object('run_status',r.status) order by q.created_at,q.id),'[]') into jobs
 from public.research_queue_jobs q left join public.research_runs r on r.study_id=q.study_id and r.id=q.run_id where q.study_id=p_study;
 select coalesce(jsonb_agg(jsonb_set(to_jsonb(e),'{details}',e.details-'actor_id') order by e.created_at,e.id),'[]') into events from public.research_queue_events e where e.study_id=p_study;
 return jsonb_build_object('jobs',jobs,'events',events);
end $$;

revoke all on function public.research_queue_definition_immutable(),public.research_queue_enqueue(uuid,uuid,uuid,jsonb,text),public.research_queue_claim(uuid),public.research_queue_finish(uuid,uuid,jsonb,uuid,text,jsonb),public.research_queue_action(uuid,uuid,uuid,uuid,text,text,jsonb,uuid),public.research_queue_snapshot(uuid,uuid) from public,anon,authenticated;
grant execute on function public.research_queue_enqueue(uuid,uuid,uuid,jsonb,text),public.research_queue_claim(uuid),public.research_queue_finish(uuid,uuid,jsonb,uuid,text,jsonb),public.research_queue_action(uuid,uuid,uuid,uuid,text,text,jsonb,uuid),public.research_queue_snapshot(uuid,uuid) to service_role;
notify pgrst,'reload schema';
commit;
