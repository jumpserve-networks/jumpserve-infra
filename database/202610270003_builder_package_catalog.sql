begin;
create table public.research_builder_packages(
 id uuid primary key references public.research_model_dispatches(id),study_id uuid not null,task_id uuid not null,source_id uuid not null,
 project_artifact_id uuid not null,wrapper_artifact_id uuid not null,manifest_artifact_id uuid not null,candidate_artifact_id uuid not null,
 version text not null check(version='research-built-package-v1'),status text not null check(status='candidate'),
 created_at timestamptz not null default clock_timestamp(),
 foreign key(study_id,task_id) references public.research_autonomy_tasks(study_id,id),
 foreign key(study_id,source_id) references public.research_sources(study_id,id),
 foreign key(study_id,project_artifact_id) references public.research_artifacts(study_id,id),
 foreign key(study_id,wrapper_artifact_id) references public.research_artifacts(study_id,id),
 foreign key(study_id,manifest_artifact_id) references public.research_artifacts(study_id,id),
 foreign key(study_id,candidate_artifact_id) references public.research_artifacts(study_id,id)
);
alter table public.research_builder_packages enable row level security;
revoke all on public.research_builder_packages from public,anon,authenticated;
grant select,insert on public.research_builder_packages to service_role;
create trigger research_builder_packages_immutable before update or delete on public.research_builder_packages for each row execute function public.research_immutable();
create function public.research_builder_package(p_dispatch uuid,p_token uuid,p_project uuid,p_wrapper uuid,p_manifest uuid,p_candidate uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.research_model_dispatches;r public.research_builder_packages;source uuid; begin
 select * into strict d from public.research_model_dispatches where id=p_dispatch for update;
 if d.status<>'running' or d.lease_token is distinct from p_token or d.lease_until<=clock_timestamp() then raise exception 'Current fenced builder dispatch required';end if;
 select c.source_id into strict source from public.research_claims c join public.research_autonomy_tasks t on t.claim_id=c.id and t.study_id=c.study_id where t.id=d.task_id and t.stage='building';
 if exists(select 1 from (values(p_project,'builder-frozen-project'),(p_wrapper,'builder-server-wrapper'),(p_manifest,'builder-original-manifest'),(p_candidate,'builder-compiled-candidate')) inputs(id,kind)
  where not exists(select 1 from public.research_artifacts a where a.study_id=d.study_id and a.id=inputs.id and a.provenance->>'kind'=inputs.kind and a.provenance->>'dispatch_id'=d.id::text))
  then raise exception 'Original builder project, wrapper, manifest and compiled candidate must be retained first';end if;
 select * into r from public.research_builder_packages where id=d.id;
 if found then
  if (r.project_artifact_id,r.wrapper_artifact_id,r.manifest_artifact_id,r.candidate_artifact_id) is distinct from (p_project,p_wrapper,p_manifest,p_candidate) then raise exception 'Builder candidate revision is immutable';end if;return to_jsonb(r);
 end if;
 insert into public.research_builder_packages(id,study_id,task_id,source_id,project_artifact_id,wrapper_artifact_id,manifest_artifact_id,candidate_artifact_id,version,status)
 values(d.id,d.study_id,d.task_id,source,p_project,p_wrapper,p_manifest,p_candidate,'research-built-package-v1','candidate') returning * into r;
 return to_jsonb(r);
end $$;
revoke all on function public.research_builder_package(uuid,uuid,uuid,uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function public.research_builder_package(uuid,uuid,uuid,uuid,uuid,uuid) to service_role;

-- Lost native requests stay unknown even if a later controller is recovered.
-- Fence all subsequent requests for that claim until explicit reconciliation.
do $migration$ declare definition text;old text;begin
 definition=pg_get_functiondef('public.research_builder_call(text,jsonb)'::regprocedure);
 old=$old$where dispatch_id=d.id and status in ('running','unknown')$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected builder in-flight guard';end if;
 execute replace(definition,old,$new$where task_id=t.id and status in ('running','unknown')$new$);
 definition=pg_get_functiondef('public.research_model_dispatch(text,jsonb)'::regprocedure);
 old=$old$elsif p_operation='claim' then$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected model worker claim gate';end if;
 execute replace(definition,old,$new$elsif p_operation='claim' then
  update public.research_builder_calls c set status='unknown',reason='Model worker lease expired; reconcile original request before another call.',ended_at=clock_timestamp()
   from public.research_model_dispatches expired_dispatch where c.dispatch_id=expired_dispatch.id and c.status='running' and expired_dispatch.status='running' and expired_dispatch.lease_until<=clock_timestamp();$new$);
end $migration$;
notify pgrst,'reload schema';
commit;
