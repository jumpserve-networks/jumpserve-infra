-- Unchanged owner plans retain their version and review budget. Adoption is audited.
begin;
create function public.research_reuse_claim_packet(p_study uuid,p_actor uuid,p_id uuid,p_packet uuid,p_run uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare packet public.research_idea_packets; latest_id uuid; attempt public.research_idea_runs;
 prior public.research_audit_events;
 result jsonb;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0));
 perform public.research_idea_owner(p_study,p_actor);
 if not exists(select 1 from public.research_claim_designs where study_id=p_study) then
  raise exception 'A source-bound paper claim workspace is required'; end if;
 select * into strict packet from public.research_idea_packets where study_id=p_study and id=p_packet;
 result=to_jsonb(packet)||jsonb_build_object('adoption',jsonb_build_object(
  'kind','reuse-current-packet','request_id',p_id,'run_id',p_run,'packet_id',p_packet,
  'packet_sha256',packet.sha256,'new_packet_created',false,'review_budget_preserved',true));
 select * into prior from public.research_audit_events where study_id=p_study and action='claim:reuse-packet'
  and details->>'request_id'=p_id::text order by id limit 1;
 if found then
  if prior.actor_id<>p_actor or prior.details->>'packet_id' is distinct from p_packet::text
   or prior.details->>'run_id' is distinct from p_run::text or prior.details->>'packet_sha256' is distinct from packet.sha256 then
   raise exception 'Reuse request ID already identifies different evidence'; end if;
  return result;
 end if;
 select id into latest_id from public.research_idea_packets where study_id=p_study order by version desc limit 1;
 if latest_id is distinct from p_packet then raise exception 'Draft changed; reload before reusing a plan'; end if;
 select * into strict attempt from public.research_idea_runs where id=p_run and study_id=p_study;
 if attempt.actor_id<>p_actor or attempt.packet_id<>p_packet or attempt.task<>'planning' or attempt.status<>'complete'
  or attempt.output->>'response_version' is distinct from 'claim-design-response-v3'
  or attempt.output->>'response_mode' is distinct from 'reuse'
  or attempt.output->'proposal' is distinct from packet.document
  or attempt.output->'questions' is distinct from '[]'::jsonb
  or attempt.output->'decision_policy'->>'origin' is distinct from 'server-policy'
  or attempt.output->'decision_policy'->'model_authored' is distinct from 'false'::jsonb
  or attempt.output->'decision_policy'->'protocol_reused' is distinct from 'true'::jsonb
  or packet.document->'protocol'->'decision_policy' is distinct from
   '{"version":"claim-decision-policy-v1","mode":"descriptive-only","sha256":"15f01c489c51ca834279f6226bd9048da3abd5e2334d363daba33a7b3e1ad6f3"}'::jsonb
  or not exists(select 1 from public.agent_prompt_versions where id=attempt.prompt_version_id
   and module_id='research-claim-design' and published_at is not null)
 then raise exception 'A complete unchanged source-bound reuse answer is required'; end if;
 insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'claim:reuse-packet',
  jsonb_build_object('request_id',p_id,'run_id',p_run,'packet_id',p_packet,'packet_sha256',packet.sha256,
   'packet_version',packet.version,'new_packet_created',false,'review_budget_preserved',true));
 return result;
end $$;
revoke all on function public.research_reuse_claim_packet(uuid,uuid,uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function public.research_reuse_claim_packet(uuid,uuid,uuid,uuid,uuid) to service_role;
notify pgrst,'reload schema';
commit;
