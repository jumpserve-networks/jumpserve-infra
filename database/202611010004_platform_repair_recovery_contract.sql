begin;
select pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));

-- Installed schema/code is evidence, not a new transport capability. Keep this
-- helper private beneath the existing worker/token/authorization-checked RPC.
create function public.platform_repair_recovery_contract() returns jsonb
language sql stable security definer set search_path='' as $$
 select jsonb_build_object(
  'version','platform-repair-recovery-contract-v1',
  'queued_admission',jsonb_build_object(
   'version','queued-dispatch-reconciliation-v1',
   'read',jsonb_build_object('relation','research_queued_dispatch_reconciliations',
    'columns',jsonb_build_array('dispatch_id','study_id','task_id','request_sha256','snapshot_raw','snapshot_sha256','parent_turn_status','proof','created_at'),
    'order','created_at.asc,dispatch_id.asc','access','service-only',
    'actual_columns',(select jsonb_agg(a.attname order by a.attnum) from pg_catalog.pg_attribute a
     where a.attrelid='public.research_queued_dispatch_reconciliations'::regclass and a.attnum>0 and not a.attisdropped)),
   'reconcile',jsonb_build_object('signature','public.research_model_reconcile_queued(uuid,text)',
    'definition',pg_get_functiondef('public.research_model_reconcile_queued(uuid,text)'::regprocedure),
    'sha256',encode(sha256(convert_to(pg_get_functiondef('public.research_model_reconcile_queued(uuid,text)'::regprocedure),'UTF8')),'hex')),
   'constraints',(select jsonb_agg(pg_get_constraintdef(c.oid) order by c.conname) from pg_catalog.pg_constraint c
    where c.conrelid='public.research_queued_dispatch_reconciliations'::regclass),
   'triggers',(select jsonb_agg(pg_get_triggerdef(t.oid) order by t.tgname) from pg_catalog.pg_trigger t
    where t.tgrelid='public.research_queued_dispatch_reconciliations'::regclass and not t.tgisinternal),
   'permissions',jsonb_build_object('service_select',has_table_privilege('service_role','public.research_queued_dispatch_reconciliations','SELECT'),
    'browser_select',has_table_privilege('anon','public.research_queued_dispatch_reconciliations','SELECT') or has_table_privilege('authenticated','public.research_queued_dispatch_reconciliations','SELECT'),
    'service_mutation',has_table_privilege('service_role','public.research_queued_dispatch_reconciliations','INSERT,UPDATE,DELETE'),
    'browser_reconcile',has_function_privilege('anon','public.research_model_reconcile_queued(uuid,text)','EXECUTE') or has_function_privilege('authenticated','public.research_model_reconcile_queued(uuid,text)','EXECUTE'))),
  'scope','Read-only installed recovery contract. The model cannot invoke the controller adapter. Pre-transport queue closure proves neither container cleanup nor scientific readiness; unknown calls, original outcomes, budgets and deadlines remain unchanged.')
$$;
revoke all on function public.platform_repair_recovery_contract() from public,anon,authenticated,service_role;

alter function public.platform_repair_context_data(uuid) rename to platform_repair_context_data_before_contract_v3;
revoke all on function public.platform_repair_context_data_before_contract_v3(uuid) from public,anon,authenticated,service_role;
create function public.platform_repair_context_data(p_task uuid) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare data jsonb;contract jsonb;diagnoses jsonb;binding text;begin
 data=public.platform_repair_context_data_before_contract_v3(p_task);
 if data is null then return null;end if;
 contract=public.platform_repair_recovery_contract();
 select coalesce(jsonb_agg(value order by created_at desc,id),'[]') into diagnoses from (
  select a.id,a.created_at,jsonb_build_object('id',a.id,'sha256',a.sha256,'byte_count',a.byte_count,
   'storage_path',a.storage_path,'provenance',a.provenance) value
  from public.research_artifacts a where a.study_id=(data->>'assessment_id')::uuid
   and a.provenance->>'kind'='autonomous-repair-diagnosis'
   -- save_diagnosis records the pointer in the repair evidence even when a
   -- waiting diagnosis has not been copied into task.context.repair_packet.
   and exists(select 1 from public.research_autonomy_repairs r where r.study_id=a.study_id
    and r.task_id=(data->>'assessment_task_id')::uuid and r.evidence->'diagnosis'->>'artifact_id'=a.id::text)
  order by a.created_at desc,a.id limit 3)x;
 binding=encode(sha256(convert_to(contract::text,'UTF8')),'hex');
 data=data||jsonb_build_object('recovery_contract',contract,'recovery_contract_sha256',binding,
  'current_diagnoses',diagnoses);
 -- Deliver referenced originals first while retaining the twelve-artifact
 -- bound and de-duplicating the older task-context view.
 -- Explicit ordering and limit live in a subquery so aggregation cannot hide
 -- truncation. Original references remain in current_diagnoses/context history.
 data=jsonb_set(data,'{artifacts}',(select coalesce(jsonb_agg(value order by rank,ordinal),'[]') from (
  select value,rank,ordinal from (
   select distinct on (value->>'id') value,rank,ordinal from (
    select value,0 rank,ordinality ordinal from jsonb_array_elements(diagnoses) with ordinality
    union all select value,1 rank,ordinality ordinal from jsonb_array_elements(data->'artifacts') with ordinality)x
   order by value->>'id',rank,ordinal)y order by rank,ordinal limit 12)z));
 return data||jsonb_build_object('evidence_revision',encode(sha256(convert_to(jsonb_build_object(
  'incident_evidence_revision',data->>'evidence_revision','recovery_contract_sha256',binding,
  'diagnoses',diagnoses)::text,'UTF8')),'hex'));
end$$;
revoke all on function public.platform_repair_context_data(uuid) from public,anon,authenticated,service_role;
notify pgrst,'reload schema';
commit;
