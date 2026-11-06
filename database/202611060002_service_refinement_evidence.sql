begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- A changed objective is new evidence, not permission to overwrite the original
-- request or endlessly activate the same fixed adapter under fresh identities.
create table public.platform_service_work_refinements (
 id uuid primary key,parent_task_id uuid not null references public.platform_tasks(id),
 request_id uuid not null references public.platform_service_work_requests(id),
 spec jsonb not null,spec_sha256 text not null check(spec_sha256~'^[a-f0-9]{64}$'),
 artifact_id uuid not null references public.platform_artifacts(id),created_at timestamptz not null default clock_timestamp(),
 unique(parent_task_id,spec_sha256)
);
alter table public.platform_service_work_refinements enable row level security;
revoke all on public.platform_service_work_refinements from public,anon,authenticated,service_role;
grant select on public.platform_service_work_refinements to service_role;
create trigger service_refinement_immutable before update or delete on public.platform_service_work_refinements
 for each row execute function public.platform_immutable();

create table public.research_runtime_observations (
 artifact_id uuid primary key,study_id uuid not null,task_id uuid not null,dispatch_id uuid not null references public.research_model_dispatches(id),
 sha256 text not null check(sha256~'^[a-f0-9]{64}$'),proof jsonb not null,created_at timestamptz not null default clock_timestamp(),
 foreign key(study_id,task_id) references public.research_autonomy_tasks(study_id,id),
 foreign key(study_id,artifact_id) references public.research_artifacts(study_id,id)
);
alter table public.research_runtime_observations enable row level security;
revoke all on public.research_runtime_observations from public,anon,authenticated,service_role;
grant select on public.research_runtime_observations to service_role;
create trigger runtime_observation_immutable before update or delete on public.research_runtime_observations
 for each row execute function public.research_immutable();

do $migration$ declare definition text;old text;begin
 definition=pg_get_functiondef('public.platform_service_work(text,uuid,uuid,uuid,jsonb)'::regprocedure);
 old=$old$if exists(select 1 from public.platform_service_work_requests where parent_task_id=t.id and profile=v_spec->>'profile') then raise exception 'Retain the original service profile request';end if;$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected original service refinement boundary';end if;
 definition=replace(definition,old,$new$
 select * into q from public.platform_service_work_requests where parent_task_id=t.id and profile=v_spec->>'profile';
 if found then
  if exists(select 1 from public.platform_service_work_refinements r where r.id=ident
   and (r.parent_task_id,r.request_id,r.spec,r.artifact_id) is distinct from (t.id,q.id,v_spec,(p_payload->>'artifact_id')::uuid))
   then raise exception 'Service refinement identity differs';end if;
  insert into public.platform_service_work_refinements(id,parent_task_id,request_id,spec,spec_sha256,artifact_id)
   values(ident,t.id,q.id,v_spec,binding,(p_payload->>'artifact_id')::uuid) on conflict(parent_task_id,spec_sha256) do nothing;
  if found then insert into public.platform_events(id,task_id,actor,kind,message,details)
   values(ident,t.id,'service-broker','service-refinement-recorded',
    'Additional service requirements retained separately. The existing activation proves only its fixed adapter; no new capability, release or assessment outcome is inferred.',
    jsonb_build_object('request_id',q.id,'profile',q.profile,'spec_sha256',binding,'scientific_completion',false));end if;
  return jsonb_build_object('id',q.id,'implementation_task_id',q.implementation_task_id,'profile',q.profile,
   'requires_implementation',true,'refinement_spec_sha256',binding,
   'reason','Additional requirements exceed the existing fixed service contract. Read the retained worker runtime diagnostics; implement and qualify any remaining adapter rather than reactivating this manifest.',
   'scientific_completion',false);
 end if;
 $new$);
 execute definition;
end $migration$;

-- These worker-generated, task-bound records describe observations, not a claim
-- that a generic evidence activation implemented arbitrary requested features.
do $migration$ declare definition text;old text;begin
 definition=pg_get_functiondef('public.platform_service_evidence(uuid)'::regprocedure);
 old=$old$'schema',(select jsonb_object_agg(table_name,cols)$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected original service evidence projection';end if;
 definition=replace(definition,old,$new$
 'runtime_observations',coalesce((select jsonb_agg(to_jsonb(x)) from (
  select a.id,a.sha256,a.byte_count,a.created_at,a.provenance from public.research_artifacts a where a.study_id=b.study_id
   and a.provenance->>'task_id'=b.assessment_task_id::text
   and a.provenance->>'kind' in ('worker-runtime-diagnostics-v1','worker-installed-source-v1')
   and exists(select 1 from public.research_runtime_observations observed where observed.study_id=b.study_id and observed.task_id=b.assessment_task_id
    and (observed.artifact_id=a.id or exists(select 1 from jsonb_array_elements(observed.proof->'sources') source
      where source->'artifact'->>'artifact_id'=a.id::text and source->>'sha256'=a.sha256)))
   order by a.created_at desc,a.id limit 32)x),'[]'),
 'schema',(select jsonb_object_agg(table_name,cols)$new$);
 execute definition;
end $migration$;
revoke all on function public.platform_service_evidence(uuid) from public,anon,authenticated,service_role;
notify pgrst,'reload schema';
commit;
