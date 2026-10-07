begin;

-- Preparation metadata and retained compiled plans are private. Scientific
-- records still use the existing append-only tables and publication boundary.
create table public.research_prepared_plans (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 plan_id text not null check(plan_id ~ '^[a-z0-9][a-z0-9-]{0,79}$'), manifest_sha256 text not null check(manifest_sha256 ~ '^[a-f0-9]{64}$'),
 original_artifact_id uuid not null, compiled_artifact_id uuid not null,
 jobs jsonb not null check(jsonb_typeof(jobs)='array' and jsonb_array_length(jobs) between 1 and 100),
 provenance jsonb not null check(jsonb_typeof(provenance)='object'), created_at timestamptz not null default clock_timestamp(),
 unique(study_id,id), unique(study_id,manifest_sha256),
 foreign key(study_id,original_artifact_id) references public.research_artifacts(study_id,id),
 foreign key(study_id,compiled_artifact_id) references public.research_artifacts(study_id,id)
);
alter table public.research_prepared_plans enable row level security;
revoke all on public.research_prepared_plans from public,anon,authenticated;
grant all on public.research_prepared_plans to service_role;
create trigger research_prepared_plan_immutable before update or delete on public.research_prepared_plans
 for each row execute function public.research_immutable();

create function public.research_prepare_plan(p_study uuid,p_actor uuid,p_id uuid,p_request uuid,p_plan jsonb,p_records jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare prior public.research_prepared_plans; original public.research_artifacts; compiled public.research_artifacts; j jsonb; attempts jsonb; begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0));
 if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Study not found'; end if;
 if jsonb_typeof(p_records) is distinct from 'array' or jsonb_array_length(p_records)>1000 or
  exists(select 1 from jsonb_array_elements(p_records) e where e->>'kind' is null or e->>'kind' not in ('artifacts','sources','claims','configurations','protocols','campaigns','claim_checks','assessments','gaps')) then raise exception 'Invalid preparation record bundle'; end if;
 select * into prior from public.research_prepared_plans where id=p_id;
 if found then
  if prior.study_id<>p_study or prior.manifest_sha256 is distinct from p_plan->>'manifest_sha256' or prior.plan_id is distinct from p_plan->>'plan_id' then raise exception 'Prepared plan ID already identifies different original bytes'; end if;
  -- Concurrent compilation can produce different freeze timestamps. Retain its
  -- verified private bytes as attempt artifacts; the first saved scientific
  -- records/protocols win and are never replaced with the later compilation.
  select coalesce(jsonb_agg(e),'[]'::jsonb) into attempts from jsonb_array_elements(p_records) e
   where e->>'kind'='artifacts' and not exists(select 1 from public.research_artifacts a where a.id=(e->'record'->>'id')::uuid);
  perform public.research_append_bundle(p_study,p_actor,attempts);
  insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'prepare-plan:replayed',jsonb_build_object('request_id',p_request,'prepared_id',p_id,'manifest_sha256',prior.manifest_sha256,'retained_attempt_artifacts',attempts));
  return to_jsonb(prior);
 end if;
 if (select count(*) from public.research_prepared_plans where study_id=p_study)>=100 then raise exception 'Preparation history budget exhausted'; end if;
 if jsonb_typeof(p_plan->'jobs') is distinct from 'array' or jsonb_array_length(p_plan->'jobs') not between 1 and 100 then raise exception 'Bounded campaign definitions required'; end if;
 perform public.research_append_bundle(p_study,p_actor,p_records);
 select * into original from public.research_artifacts where study_id=p_study and id=(p_plan->>'original_artifact_id')::uuid;
 select * into compiled from public.research_artifacts where study_id=p_study and id=(p_plan->>'compiled_artifact_id')::uuid;
 if original.id is null or compiled.id is null or original.sha256 is distinct from p_plan->>'manifest_sha256' or original.byte_count>1500000 or compiled.byte_count>4000000 then raise exception 'Verified retained originals required'; end if;
 if (select count(distinct value->>'id') from jsonb_array_elements(p_plan->'jobs'))<>jsonb_array_length(p_plan->'jobs') then raise exception 'Duplicate prepared job identities'; end if;
 for j in select value from jsonb_array_elements(p_plan->'jobs') loop
  if j->>'execution_mode' is null or j->>'execution_mode' not in ('automatic','manual') or j->>'id' is null or j->>'title' is null or not exists(select 1 from public.research_campaigns where study_id=p_study and id=(j->>'campaign_id')::uuid) or
   not exists(select 1 from public.research_claim_checks where study_id=p_study and campaign_id=(j->>'campaign_id')::uuid and applicability='applicable') then raise exception 'Every prepared job needs a linked sourced campaign'; end if;
 end loop;
 insert into public.research_prepared_plans(id,study_id,plan_id,manifest_sha256,original_artifact_id,compiled_artifact_id,jobs,provenance)
 values(p_id,p_study,p_plan->>'plan_id',p_plan->>'manifest_sha256',(p_plan->>'original_artifact_id')::uuid,(p_plan->>'compiled_artifact_id')::uuid,p_plan->'jobs',p_plan->'provenance') returning * into prior;
 insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'prepare-plan:created',jsonb_build_object('request_id',p_request,'prepared_id',p_id,'manifest_sha256',prior.manifest_sha256,'compiled_sha256',compiled.sha256,'planned_jobs',jsonb_array_length(prior.jobs)));
 return to_jsonb(prior);
end $$;
revoke all on function public.research_prepare_plan(uuid,uuid,uuid,uuid,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.research_prepare_plan(uuid,uuid,uuid,uuid,jsonb,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
