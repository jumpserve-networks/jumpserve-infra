begin;
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
alter function public.platform_repair_context_data(uuid) rename to platform_repair_context_data_before_delivery_v5;
revoke all on function public.platform_repair_context_data_before_delivery_v5(uuid) from public,anon,authenticated,service_role;

create function public.platform_repair_context_data(p_task uuid) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare data jsonb;documents jsonb;preferred jsonb;begin
 data=public.platform_repair_context_data_before_delivery_v5(p_task);
 if data is null then return null;end if;
 -- Choose recorded incident turns first. Newer polling/transport artifacts
 -- cannot displace the manifest/checkpoint pair belonging to that incident.
 with dispatches as (
  select d.*,row_number() over(order by
   case when exists(select 1 from public.research_autonomy_repairs r where r.study_id=d.study_id and r.task_id=d.task_id
     and r.incident_raw::jsonb->>'failed_turn_id'=d.id::text) then 0 else 1 end,d.created_at desc,d.id) ordinal
  from public.research_model_dispatches d where d.study_id=(data->>'assessment_id')::uuid
   and d.task_id=(data->>'assessment_task_id')::uuid
 ), chosen as (select * from dispatches where ordinal<=3), candidates as (
  select d.id dispatch_id,d.ordinal,a.*,
   case when a.provenance->>'filename'='context-delivery.json' then 0
    when a.provenance->>'filename' in ('checkpoint.zip','failed-checkpoint.zip','post-validation-checkpoint.zip') then 1
    when a.provenance->>'filename'='receipt.json' then 2
    when a.provenance->>'filename'='task.txt' then 3
    when a.provenance->>'filename'='action-policy.json' then 4
    when a.provenance->>'filename'=d.provenance->'denied_request'->>'filename'
     and a.provenance->>'filename'~'^native-request-[a-f0-9]{64}\.json$' then 5
    when a.provenance->>'filename'='stdout.bin' then 6
    when a.provenance->>'filename'='stderr.bin' then 7 end role,
   a.id::text in (d.provenance->'checkpoint'->>'artifact_id',d.provenance->'context_delivery'->>'artifact_id') exact_pointer
  from chosen d join public.research_artifacts a on a.study_id=d.study_id and a.provenance->>'dispatch_id'=d.id::text
 ), refs as (
  select distinct on(dispatch_id,role) dispatch_id,ordinal,role,
   jsonb_build_object('id',id,'sha256',sha256,'byte_count',byte_count,'storage_path',storage_path,'provenance',provenance) artifact
  from candidates where role is not null
  order by dispatch_id,role,exact_pointer desc nulls last,created_at desc,id
 )
 select (select coalesce(jsonb_agg(jsonb_build_object('dispatch_id',d.id,'request_sha256',d.request_sha256,'status',d.status,
    'denied_request_declared',d.provenance?'denied_request',
    'references',coalesce((select jsonb_agg(jsonb_build_object('role',(array['context_delivery','checkpoint','receipt','bootstrap','action_policy','denied_request','stdout','stderr'])[r.role+1],
     'artifact_id',r.artifact->'id','sha256',r.artifact->'sha256') order by r.role) from refs r where r.dispatch_id=d.id),'[]'),
    'scope','Incident-specific originals. Views are passive, bounded and redacted; missing delivered fields are not evidence of absent originals or safe replay.') order by d.ordinal),'[]') from chosen d),
  (select coalesce(jsonb_agg(artifact order by ordinal,role),'[]') from refs)
 into documents,preferred;
 data=jsonb_set(data,'{artifacts}',(select coalesce(jsonb_agg(value order by priority),'[]') from (
  select value,priority from (
   select distinct on(value->>'id') value,priority from (
    select value,ordinality::integer priority from jsonb_array_elements(preferred) with ordinality
    union all
    select value,case when value->'provenance'->>'kind'='autonomous-repair-diagnosis' then -100 else 1000 end+ordinality::integer priority
     from jsonb_array_elements(data->'artifacts') with ordinality)x
   order by value->>'id',priority)y order by priority limit 12)z));
 return data||jsonb_build_object('incident_documents',documents,'evidence_revision',encode(sha256(convert_to(
  jsonb_build_object('previous',data->>'evidence_revision','incident_documents',documents,'delivered_artifacts',data->'artifacts')::text,'UTF8')),'hex'));
end$$;
revoke all on function public.platform_repair_context_data(uuid) from public,anon,authenticated,service_role;
notify pgrst,'reload schema';
commit;
