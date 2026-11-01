begin;
-- Status polling must not deserialize the original 96-KB request merely to
-- remove it from the response. All admissions and uncertain-call guards stay
-- in the original implementation; only the existing read projection changes.
alter function public.research_model_dispatch(text,jsonb) rename to research_model_dispatch_before_polling_v1;
revoke all on function public.research_model_dispatch_before_polling_v1(text,jsonb) from public,anon,authenticated,service_role;
create function public.research_model_dispatch(p_operation text,p_payload jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;begin
 if p_operation='result' then
  select to_jsonb(metadata) into strict result from (
   select id,study_id,task_id,runtime,request_sha256,status,lease_until,
    response_artifact_id,response_sha256,provenance,created_at,ended_at
   from public.research_model_dispatches
   where id=(p_payload->>'id')::uuid and study_id=(p_payload->>'study_id')::uuid
  ) metadata;
  return result;
 end if;
 return public.research_model_dispatch_before_polling_v1(p_operation,p_payload);
end$$;
revoke all on function public.research_model_dispatch(text,jsonb) from public,anon,authenticated;
grant execute on function public.research_model_dispatch(text,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
