begin;
-- Private execution control. Public results use the existing reviewed research
-- records; raw packages, launch capabilities and machine credentials stay private.
create table public.research_network_executions (
 job_id uuid primary key references public.research_queue_jobs(id),
 study_id uuid not null references public.research_studies(id), owner_id uuid not null,
 runner text not null check(runner in ('emulated-netem-v1','real-world-iperf-v1','custom-package-v1')),
 spec jsonb not null, spec_sha256 text not null check(spec_sha256 ~ '^[a-f0-9]{64}$'),
 phase text not null default 'pending' check(phase in ('pending','dispatching','running','completed','failed','cancelled')),
 cancel_requested boolean not null default false, launch_claimed_at timestamptz,
 started_at timestamptz not null default clock_timestamp(), deadline timestamptz not null,
 data jsonb not null default '{}'::jsonb, ingest_hash text, created_at timestamptz not null default clock_timestamp(),
 foreign key(study_id,job_id) references public.research_queue_jobs(study_id,id)
);
alter table public.research_network_executions enable row level security;
revoke all on public.research_network_executions from public,anon,authenticated;
grant select,insert,update on public.research_network_executions to service_role;

create function public.research_network_immutable() returns trigger language plpgsql set search_path='' as $$ begin
 if (to_jsonb(new)-array['phase','cancel_requested','launch_claimed_at','data','ingest_hash']) is distinct from
    (to_jsonb(old)-array['phase','cancel_requested','launch_claimed_at','data','ingest_hash']) then raise exception 'Frozen networking execution identity is immutable'; end if;
 if old.phase in ('completed','failed','cancelled') and (new.phase<>old.phase or new.data is distinct from old.data) then raise exception 'Terminal networking evidence is immutable'; end if;
 return new;
end $$;
create trigger research_network_immutable before update on public.research_network_executions for each row execute function public.research_network_immutable();

create function public.research_network_begin(p_job uuid,p_token uuid,p_spec jsonb,p_sha text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare j public.research_queue_jobs; c public.research_campaigns; p public.research_protocols; n public.research_network_executions; begin
 select * into j from public.research_queue_jobs where id=p_job for update;
 if j.status is distinct from 'running' or j.lease_token is distinct from p_token or j.lease_until<=clock_timestamp() then raise exception 'Current worker lease required'; end if;
 select * into c from public.research_campaigns where study_id=j.study_id and id=j.campaign_id;
 select * into p from public.research_protocols where study_id=j.study_id and id=c.protocol_id;
 if jsonb_typeof(p_spec) is distinct from 'object' or jsonb_typeof(p_spec->'configuration_index') is distinct from 'number' or jsonb_typeof(p_spec->'replication') is distinct from 'number' then raise exception 'Networking invocation identities required'; end if;
 if c.adapter<>'network-execution-v1' or (p_spec->>'configuration_index')::integer not between 0 and jsonb_array_length(p.document->'configurations')-1 or p_sha is distinct from j.request->>'input_sha256' or
    p_spec->>'version' is distinct from 'network-execution-v1' or p_spec->>'runner' is distinct from p.document->'execution'->>'runner' or
    p_spec->'limits' is distinct from p.document->'execution'->'limits' or p_spec->'metrics' is distinct from (select jsonb_agg(jsonb_build_object('name',m->'name','units',m->'units')) from jsonb_array_elements(p.document->'metrics') m) or
    p_spec->'config' is distinct from p.document->'configurations'->((p_spec->>'configuration_index')::integer)->'details'->'test_config' or
    p_spec->>'configuration_identity' is distinct from p.document->'configurations'->((p_spec->>'configuration_index')::integer)->>'identity' or
    (p_spec->>'replication')::integer not between 0 and (p.document->'execution'->>'replications')::integer-1 then raise exception 'Networking specification differs from frozen campaign'; end if;
 select * into n from public.research_network_executions where job_id=p_job;
 if found then
  if n.spec is distinct from p_spec or n.spec_sha256<>p_sha then raise exception 'Networking job identity already used'; end if;
 else
  insert into public.research_network_executions(job_id,study_id,owner_id,runner,spec,spec_sha256,deadline)
   select j.id,j.study_id,o.owner_id,p_spec->>'runner',p_spec,p_sha,clock_timestamp()+make_interval(secs=>(p_spec->'limits'->>'wall_seconds')::integer)
   from public.research_study_owners o where o.study_id=j.study_id returning * into n;
  insert into public.research_queue_events values(gen_random_uuid(),j.study_id,j.id,'network-prepared','running','Frozen networking invocation retained before cloud dispatch.',jsonb_build_object('runner',n.runner,'spec_sha256',n.spec_sha256,'deadline',n.deadline),default);
 end if;
 return to_jsonb(n)-array['owner_id','ingest_hash'];
end $$;

-- Direct IAM-only launchers read owner/configuration from the database. Browser
-- input never chooses an AWS function, role, account, image capability or owner.
create function public.research_network_launch(p_job uuid,p_runner text,p_claim boolean default false)
returns jsonb language plpgsql security definer set search_path='' as $$
declare n public.research_network_executions; begin
 select * into n from public.research_network_executions where job_id=p_job and runner=p_runner for update;
 if n.job_id is null then raise exception 'Saved networking invocation required'; end if;
 if p_claim then
  if n.phase<>'pending' or n.cancel_requested or n.deadline<=clock_timestamp() then return null; end if;
  if not exists(select 1 from public.research_queue_jobs where id=p_job and status='running' and lease_until>clock_timestamp()) then raise exception 'Active queue authorization required'; end if;
  update public.research_network_executions set phase='dispatching',launch_claimed_at=clock_timestamp() where job_id=p_job returning * into n;
  insert into public.research_queue_events values(gen_random_uuid(),n.study_id,n.job_id,'network-dispatch','running','One launch attempt authorized; acknowledgement loss never causes an automatic replay.',jsonb_build_object('runner',n.runner),default);
 end if;
 return to_jsonb(n);
end $$;

create function public.research_network_update(p_job uuid,p_phase text,p_data jsonb,p_ingest_hash text default null)
returns jsonb language plpgsql security definer set search_path='' as $$
declare n public.research_network_executions; begin
 select * into n from public.research_network_executions where job_id=p_job for update;
 if n.job_id is null or p_phase not in ('dispatching','running','completed','failed','cancelled') or jsonb_typeof(p_data) is distinct from 'object' then raise exception 'Invalid networking update'; end if;
 if n.phase in ('completed','failed','cancelled') then
  if p_phase<>n.phase or p_data is distinct from n.data then raise exception 'Terminal evidence cannot change'; end if;
  return to_jsonb(n)-array['owner_id','ingest_hash'];
 end if;
 if p_ingest_hash is not null and (p_ingest_hash !~ '^[a-f0-9]{64}$' or n.ingest_hash is not null and n.ingest_hash<>p_ingest_hash) then raise exception 'Launch capability cannot be replaced'; end if;
 update public.research_network_executions set phase=p_phase,data=p_data,ingest_hash=coalesce(ingest_hash,p_ingest_hash) where job_id=p_job returning * into n;
 return to_jsonb(n)-array['owner_id','ingest_hash'];
end $$;

create function public.research_network_pending() returns jsonb language sql security definer set search_path='' as $$
 select coalesce(jsonb_agg(to_jsonb(q)),'[]'::jsonb) from public.research_queue_jobs q join public.research_campaigns c on c.id=q.campaign_id and c.study_id=q.study_id
 where q.status='running' and q.lease_until>clock_timestamp() and c.adapter='network-execution-v1';
$$;

create function public.research_network_cancel(p_study uuid,p_actor uuid,p_job uuid,p_id uuid,p_reason text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare n public.research_network_executions; begin
 if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Study not found'; end if;
 if length(coalesce(p_reason,'')) not between 1 and 5000 then raise exception 'Cancellation reason required'; end if;
 select * into n from public.research_network_executions where job_id=p_job and study_id=p_study for update;
 if n.job_id is null then raise exception 'Started networking invocation required; cancel unstarted work through the queue'; end if;
 if exists(select 1 from public.research_queue_events where id=p_id and (study_id<>p_study or job_id<>p_job or event<>'network-cancel' or reason<>p_reason)) then raise exception 'Cancellation identity already used'; end if;
 if not exists(select 1 from public.research_queue_events where id=p_id) then
  update public.research_network_executions set cancel_requested=true where job_id=p_job;
  insert into public.research_queue_events values(p_id,p_study,p_job,'network-cancel','running',p_reason,'{}'::jsonb,default);
 end if;
 return jsonb_build_object('cancel_requested',true,'job_id',p_job);
end $$;

create function public.research_network_token(p_job uuid,p_hash text) returns jsonb language sql security definer set search_path='' as $$
 select to_jsonb(n)-array['owner_id','ingest_hash'] from public.research_network_executions n where job_id=p_job and ingest_hash=p_hash and deadline>clock_timestamp() and phase in ('dispatching','running');
$$;

revoke all on function public.research_network_immutable(),public.research_network_begin(uuid,uuid,jsonb,text),public.research_network_launch(uuid,text,boolean),public.research_network_update(uuid,text,jsonb,text),public.research_network_pending(),public.research_network_cancel(uuid,uuid,uuid,uuid,text),public.research_network_token(uuid,text) from public,anon,authenticated;
grant execute on function public.research_network_begin(uuid,uuid,jsonb,text),public.research_network_launch(uuid,text,boolean),public.research_network_update(uuid,text,jsonb,text),public.research_network_pending(),public.research_network_cancel(uuid,uuid,uuid,uuid,text),public.research_network_token(uuid,text) to service_role;
-- Updated enqueue/claim definitions are included below. Original migrations
-- remain immutable; scientific observations and assessments are not rewritten.

create or replace function public.research_queue_enqueue(p_study uuid,p_actor uuid,p_id uuid,p_request jsonb,p_sha256 text)
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
  if (c.adapter='matched-numeric-v1' and c.experiment_type not in ('reanalysis','independent-check')) or (c.adapter='network-execution-v1' and c.experiment_type not in ('new-measurement','independent-check','broader-validation')) or c.adapter not in ('matched-numeric-v1','network-execution-v1') then raise exception 'Campaign requires a domain implementation or manual review'; end if;
  if c.adapter='matched-numeric-v1' and ((p.document->'resource_limits'->>'max_observations')::integer>1000 or (p.document->'resource_limits'->>'wall_seconds')::integer>10) then raise exception 'Protocol exceeds queue execution limits'; end if;
  if c.adapter='network-execution-v1' and to_jsonb(resources) is distinct from (select coalesce(jsonb_agg(value order by value),'[]'::jsonb) from jsonb_array_elements_text(coalesce(p.document->'execution'->'exclusive_resources','[]'::jsonb))) then raise exception 'Frozen resource locks required'; end if;
  if c.adapter='network-execution-v1' and (p.document->'execution'->>'version' is distinct from 'network-execution-v1' or p.document->'execution'->>'runner' not in ('emulated-netem-v1','real-world-iperf-v1','custom-package-v1') or (p.document->'resource_limits'->>'wall_seconds')::integer not between 60 and 3600) then raise exception 'Invalid frozen networking execution'; end if;
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


create or replace function public.research_queue_claim(p_worker uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare j public.research_queue_jobs; expired public.research_queue_jobs; begin
 perform pg_advisory_xact_lock(hashtextextended('research-queue-v1',0));
 for expired in update public.research_queue_jobs set status='expired',reason='Worker lease expired; execution/storage outcome is uncertain. No automatic retry.',lease_token=null,lease_until=null,updated_at=clock_timestamp()
  where status='running' and lease_until<=clock_timestamp() returning * loop
  insert into public.research_queue_events values(gen_random_uuid(),expired.study_id,expired.id,'lease-expired','expired',expired.reason,'{"actual_usage":null}'::jsonb,default);
 end loop;
 -- Expiry does not prove that an experiment machine was cleaned up. Keep slot
 -- and resource reservations until its private execution record is terminal.
 if (select count(*) from public.research_queue_jobs q where status='running' or status='expired' and exists(select 1 from public.research_network_executions n where n.job_id=q.id and n.phase not in ('completed','failed','cancelled')))>=4 then return null; end if;
 for j in select q.* from public.research_queue_jobs q where q.status='queued' and q.execution_mode='automatic'
  and (select count(*) from public.research_queue_jobs active where active.study_id=q.study_id and (active.status='running' or active.status='expired' and exists(select 1 from public.research_network_executions n where n.job_id=active.id and n.phase not in ('completed','failed','cancelled'))))<2
  and not exists(select 1 from public.research_queue_jobs active where (active.status='running' or active.status='expired' and exists(select 1 from public.research_network_executions n where n.job_id=active.id and n.phase not in ('completed','failed','cancelled'))) and active.exclusive_resources && q.exclusive_resources)
  and not exists(select 1 from jsonb_array_elements(q.dependencies) d
    join public.research_queue_jobs previous on previous.id=(d->>'job_id')::uuid and previous.study_id=q.study_id
    left join public.research_runs r on r.id=previous.run_id and r.study_id=q.study_id
    where (d->>'requirement'='complete-run' and (previous.status not in ('awaiting-review','reviewed') or r.status is distinct from 'complete'))
       or (d->>'requirement'='reviewed-evidence' and previous.status<>'reviewed'))
  order by q.priority,q.created_at,q.id for update skip locked loop
  update public.research_queue_jobs set status='running',reason='Bounded worker executing the frozen campaign.',lease_token=gen_random_uuid(),lease_until=clock_timestamp()+make_interval(secs=>case when exists(select 1 from public.research_campaigns c where c.id=j.campaign_id and c.study_id=j.study_id and c.adapter='network-execution-v1') then 3900 else 600 end),updated_at=clock_timestamp() where id=j.id returning * into j;
  insert into public.research_queue_events values(gen_random_uuid(),j.study_id,j.id,'claimed','running',j.reason,jsonb_build_object('worker_id',p_worker,'lease_until',j.lease_until,'global_slots',4,'study_slots',2),default);
  return to_jsonb(j);
 end loop;
 return null;
end $$;


create or replace function public.research_queue_finish(p_job uuid,p_token uuid,p_records jsonb,p_run uuid,p_error text,p_usage jsonb)
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
 update public.research_queue_jobs set status=case when exists(select 1 from public.research_network_executions n where n.job_id=p_job and n.phase='cancelled') then 'cancelled' when r.status in ('complete','partial') then 'awaiting-review' else 'failed' end,
  reason=case when r.status in ('complete','partial') then 'Evidence recorded; claim-specific assessment and review are pending.' else coalesce(p_error,r.reason,'Worker failed before a run could be recorded; usage is unavailable.') end,
  run_id=p_run,lease_token=null,lease_until=null,updated_at=clock_timestamp() where id=p_job returning * into j;
 insert into public.research_queue_events values(gen_random_uuid(),j.study_id,j.id,'finished',j.status,j.reason,jsonb_build_object('run_id',p_run,'run_status',r.status,'usage',p_usage),default);
 return to_jsonb(j)-'lease_token';
end $$;


create or replace function public.research_prepare_idea_campaign(p_study uuid,p_actor uuid,p_id uuid,p_packet uuid,p_request jsonb,p_records jsonb,p_campaign uuid,p_protocol uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare result public.research_idea_campaign_links; begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0)); perform public.research_idea_owner(p_study,p_actor);
 select * into result from public.research_idea_campaign_links where id=p_id;
 if found then
  if result.study_id<>p_study or result.packet_id<>p_packet or result.request<>p_request then raise exception 'Campaign request ID reused'; end if;
  return to_jsonb(result);
 end if;
 if jsonb_typeof(p_records) is distinct from 'array' or jsonb_array_length(p_records)>100 or
  exists(select 1 from jsonb_array_elements(p_records) r where r->>'kind' not in ('artifacts','sources','claims','configurations','protocols','campaigns','claim_checks','gaps')) then raise exception 'Invalid idea campaign bundle'; end if;
 perform public.research_append_bundle(p_study,p_actor,p_records);
 if not exists(select 1 from public.research_protocols where study_id=p_study and id=p_protocol and document->>'idea_packet_id'=p_packet::text) or
  not exists(select 1 from public.research_campaigns where study_id=p_study and id=p_campaign and protocol_id=p_protocol and adapter in ('domain-operator','network-execution-v1')) or
  not exists(select 1 from public.research_claim_checks where study_id=p_study and campaign_id=p_campaign and applicability='applicable') then raise exception 'Prepared campaign needs its reviewed protocol and explicit hypothesis link'; end if;
 insert into public.research_idea_campaign_links values(p_id,p_study,p_packet,p_campaign,p_protocol,p_request,clock_timestamp()) returning * into result;
 return to_jsonb(result);
end $$;


notify pgrst,'reload schema';
commit;
