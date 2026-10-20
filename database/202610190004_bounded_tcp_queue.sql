begin;
-- Preserve original enqueue gates; register the separately bounded TCP executor.
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
  if c.adapter='network-execution-v1' and (p.document->'execution'->>'version' is distinct from 'network-execution-v1' or p.document->'execution'->>'runner' not in ('emulated-netem-v1','real-world-iperf-v1','custom-package-v1','bounded-tcp-v1') or (p.document->'resource_limits'->>'wall_seconds')::integer not between 60 and 3600) then raise exception 'Invalid frozen networking execution'; end if;
  if c.adapter='network-execution-v1' and p.document->'execution'->>'runner'='bounded-tcp-v1' then
   if (p.document->'execution'->'limits'->>'wall_seconds')::integer is distinct from 60 or
      (p.document->'execution'->'limits'->>'max_instances')::integer is distinct from 1 then raise exception 'Bounded TCP requires its fixed queue resource envelope'; end if;
   if exists(select 1 from jsonb_array_elements(p.document->'configurations') configuration where
     jsonb_typeof(configuration->'details'->'test_config'->'payload_bytes') is distinct from 'number' or
     jsonb_typeof(configuration->'details'->'test_config'->'exchanges') is distinct from 'number' or
     jsonb_typeof(configuration->'details'->'test_config'->'application_delay_ms') is distinct from 'number' or
     (configuration->'details'->'test_config'->>'payload_bytes')::integer not between 1 and 65536 or
     (configuration->'details'->'test_config'->>'exchanges')::integer not between 1 and 16 or
     (configuration->'details'->'test_config'->>'application_delay_ms')::integer not between 0 and 20 or
     ((configuration->'details'->'test_config')-array['payload_bytes','exchanges','application_delay_ms'])<>'{}'::jsonb)
   then raise exception 'TCP configuration exceeds its immutable numeric contract'; end if;
  end if;
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
notify pgrst,'reload schema';
commit;
