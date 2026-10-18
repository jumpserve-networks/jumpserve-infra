begin;
-- Shared planning packets keep their historical idea_* names. This binding is
-- mandatory for a paper to enter that private planning/review engine.
create table public.research_claim_designs (
 id uuid primary key, study_id uuid not null unique references public.research_studies(id),
 document jsonb not null, raw_document text not null check(octet_length(raw_document)<=48000),
 sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'), source_id uuid not null, claim_id uuid not null,
 created_at timestamptz not null default clock_timestamp(),
 check(id=study_id), check(document=raw_document::jsonb),
 check(sha256=encode(sha256(convert_to(raw_document,'UTF8')),'hex')),
 foreign key(study_id,source_id) references public.research_sources(study_id,id),
 foreign key(study_id,claim_id) references public.research_claims(study_id,id)
);
alter table public.research_claim_designs enable row level security;
revoke all on public.research_claim_designs from public,anon,authenticated;
grant select,insert on public.research_claim_designs to service_role;
create trigger research_claim_design_immutable before update or delete on public.research_claim_designs
 for each row execute function public.research_immutable();

create function public.research_initialize_claim_design(p_study uuid,p_actor uuid,p_document jsonb,p_raw text,p_sha256 text,p_source jsonb,p_claim jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare existing public.research_claim_designs; begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0));
 if not exists(select 1 from public.research_studies s join public.research_study_owners o on o.study_id=s.id
  where s.id=p_study and o.owner_id=p_actor and s.study_kind='paper') then raise exception 'Private paper workspace required'; end if;
 select * into existing from public.research_claim_designs where study_id=p_study;
 if found then
  if existing.document is distinct from p_document or existing.raw_document<>p_raw or existing.sha256<>p_sha256 or
   existing.source_id::text is distinct from p_source->>'id' or existing.claim_id::text is distinct from p_claim->>'id' then raise exception 'Original paper claim context cannot be replaced'; end if;
  return to_jsonb(existing);
 end if;
 if (p_source-'id') is distinct from ((p_document->'source')-array['id','study_id','created_at']) or
  (p_claim-array['id','source_id']) is distinct from ((p_document->'claim')-array['id','source_id','study_id','created_at']) or
  p_claim->>'source_id' is distinct from p_source->>'id' then raise exception 'Retain the exact selected source and claim declarations'; end if;
 perform public.research_append_bundle(p_study,p_actor,jsonb_build_array(jsonb_build_object('kind','sources','record',p_source),jsonb_build_object('kind','claims','record',p_claim)));
 insert into public.research_claim_designs(id,study_id,document,raw_document,sha256,source_id,claim_id)
 values(p_study,p_study,p_document,p_raw,p_sha256,(p_source->>'id')::uuid,(p_claim->>'id')::uuid) returning * into existing;
 return to_jsonb(existing);
end $$;
revoke all on function public.research_initialize_claim_design(uuid,uuid,jsonb,text,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.research_initialize_claim_design(uuid,uuid,jsonb,text,text,jsonb,jsonb) to service_role;

create or replace function public.research_idea_owner(p_study uuid,p_actor uuid) returns void
language plpgsql security definer set search_path='' as $$ begin
 if not exists(select 1 from public.research_studies s join public.research_study_owners o on o.study_id=s.id
  where s.id=p_study and o.owner_id=p_actor and (s.study_kind='idea' or exists(select 1 from public.research_claim_designs d where d.study_id=s.id)))
 then raise exception 'Private planning workspace not found'; end if;
end $$;

create function public.research_claim_packet_binding() returns trigger language plpgsql set search_path='' as $$
declare d public.research_claim_designs; begin
 select * into d from public.research_claim_designs where study_id=new.study_id;
 if not found then return new; end if;
 if new.document->>'hypothesis' is distinct from d.document->'claim'->>'description' then raise exception 'Preserve the exact paper claim; scope belongs in tested conditions'; end if;
 if jsonb_typeof(new.document->'protocol')='object' then
  if new.document->'protocol'->>'hypotheses' is distinct from d.document->'claim'->>'description' then raise exception 'Preserve the exact paper hypothesis in the protocol'; end if;
  if d.document->'source'->>'sha256' is not null and not exists(select 1 from jsonb_array_elements(new.document->'protocol'->'input_versions') v where v->>'sha256'=d.document->'source'->>'sha256') then raise exception 'Retain original source hash'; end if;
  if new.document->'protocol'->'execution' is not null and new.document->'protocol'->'execution'<>'null'::jsonb and d.document->'source'->>'sha256' is null then raise exception 'Original source bytes required before automatic execution'; end if;
 end if;
 return new;
end $$;
create trigger research_claim_packet_binding before insert on public.research_idea_packets for each row execute function public.research_claim_packet_binding();

create or replace function public.research_begin_idea_run(p_study uuid,p_actor uuid,p_user text,p_id uuid,p_packet uuid,p_task text,p_session uuid,p_prompt uuid,p_model text,p_request jsonb,p_provenance jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare prior public.research_idea_runs; conversation public.agent_sessions; registration public.research_idea_sessions; begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0)); perform public.research_idea_owner(p_study,p_actor);
 select * into prior from public.research_idea_runs where id=p_id;
 if found then
  if prior.study_id<>p_study or prior.actor_id<>p_actor or prior.request<>p_request or prior.packet_id<>p_packet or prior.task<>p_task then raise exception 'Model request ID already identifies a different attempt'; end if;
  return to_jsonb(prior)||jsonb_build_object('replayed',true);
 end if;
 if not exists(select 1 from public.research_idea_packets where id=p_packet and study_id=p_study) then raise exception 'Packet not found'; end if;
 if not exists(select 1 from public.agent_prompt_settings s join public.agent_prompt_versions v on v.id=s.active_version_id
  where s.module_id=(case when exists(select 1 from public.research_claim_designs where study_id=p_study) then 'research-claim-design' else 'research-verification' end) and v.id=p_prompt and v.module_id=s.module_id and v.published_at is not null) then raise exception 'An evaluated published idea prompt must be active'; end if;
 if (select count(*) from public.research_idea_runs where study_id=p_study)>=200 then raise exception 'Idea model-call budget exhausted'; end if;
 if p_task not in ('planning','comprehension','critic') then raise exception 'Unknown idea task'; end if;
 if p_task<>'planning' and (p_session is not null or p_provenance->'history_messages' is distinct from '0'::jsonb or
   p_provenance->>'context_policy' is distinct from 'fresh-packet-only') then raise exception 'Reviews must use a fresh packet-only context'; end if;
 if p_task<>'planning' and (select count(*) from public.research_idea_runs where packet_id=p_packet and task=p_task)>=3 then raise exception 'Three attempts per review task and packet; revise the plan before further calls'; end if;
 if p_task='planning' then
  if p_session is null then raise exception 'Planning needs a study-scoped session'; end if;
  select * into conversation from public.agent_sessions where id=p_session;
  select * into registration from public.research_idea_sessions where session_id=p_session;
  if conversation.id is not null and (registration.session_id is null or registration.study_id<>p_study or registration.actor_id<>p_actor or conversation.user_id<>p_user
    or conversation.module_id<>(case when exists(select 1 from public.research_claim_designs where study_id=p_study) then 'research-claim-design' else 'research-verification' end)) then raise exception 'Planning conversation belongs to another user, study or module'; end if;
  if conversation.id is null then
   insert into public.agent_sessions(id,user_id,module_id,messages,updated_at) values(p_session,p_user,(case when exists(select 1 from public.research_claim_designs where study_id=p_study) then 'research-claim-design' else 'research-verification' end),'[]'::jsonb,clock_timestamp());
   insert into public.research_idea_sessions values(p_session,p_study,p_actor,p_user,clock_timestamp());
  end if;
  update public.research_idea_runs set status='failed',reason='Prior completion remains unconfirmed after its lease; any follow-up is a new explicitly requested attempt',ended_at=clock_timestamp()
   where session_id=p_session and status='running' and created_at<clock_timestamp()-interval '180 seconds';
  if exists(select 1 from public.research_idea_runs where session_id=p_session and status='running') then raise exception 'A planning call is still in progress; inspect its retained status'; end if;
  if (select count(*) from public.research_idea_runs where session_id=p_session)>=12 then raise exception 'Planning session budget exhausted; save the current brief and start a new session'; end if;
 end if;
 insert into public.research_idea_runs(id,study_id,packet_id,task,session_id,status,prompt_version_id,model_id,provenance,request,actor_id)
 values(p_id,p_study,p_packet,p_task,p_session,'running',p_prompt,p_model,p_provenance,p_request,p_actor) returning * into prior;
 return to_jsonb(prior)||jsonb_build_object('replayed',false);
end $$;
create or replace function public.research_guard_idea_protocol() returns trigger language plpgsql set search_path='' as $$
declare proposal public.research_idea_packets; begin
 if (select study_kind from public.research_studies where id=new.study_id)<>'idea' and not exists(select 1 from public.research_claim_designs where study_id=new.study_id) then return new; end if;
 select * into strict proposal from public.research_idea_packets where study_id=new.study_id order by version desc limit 1;
 if new.document->>'idea_packet_id' is distinct from proposal.id::text or new.document->>'idea_packet_sha256' is distinct from proposal.sha256 or
  not public.research_idea_ready(new.study_id,proposal.id,proposal.sha256) or
  (new.document-'idea_packet_id'-'idea_packet_sha256') is distinct from proposal.document->'protocol' then raise exception 'Freeze the reviewed current candidate protocol; material changes require another packet and reviews'; end if;
 return new;
end $$;
create or replace function public.research_guard_idea_queue() returns trigger language plpgsql set search_path='' as $$
declare proposal public.research_idea_packets; protocol public.research_protocols; begin
 if (select study_kind from public.research_studies where id=new.study_id)<>'idea' and not exists(select 1 from public.research_claim_designs where study_id=new.study_id) then return new; end if;
 select * into strict proposal from public.research_idea_packets where study_id=new.study_id order by version desc limit 1;
 select p.* into strict protocol from public.research_protocols p join public.research_campaigns c on c.protocol_id=p.id and c.study_id=p.study_id where c.id=new.campaign_id and c.study_id=new.study_id;
 if protocol.document->>'idea_packet_id' is distinct from proposal.id::text or not public.research_idea_ready(new.study_id,proposal.id,proposal.sha256) then raise exception 'Current idea packet readiness is required for a new queue job'; end if;
 return new;
end $$;

create function public.research_claim_campaign_binding() returns trigger language plpgsql set search_path='' as $$
declare p public.research_protocols; begin
 if not exists(select 1 from public.research_claim_designs where study_id=new.study_id) then return new; end if;
 select * into strict p from public.research_protocols where study_id=new.study_id and id=new.protocol_id;
 if new.stage is distinct from p.document->>'stage' or new.experiment_type is distinct from p.document->>'experiment_type' then raise exception 'Use the reviewed campaign stage and experimental method'; end if;
 return new;
end $$;
create trigger research_claim_campaign_binding before insert on public.research_campaigns for each row execute function public.research_claim_campaign_binding();
revoke all on function public.research_claim_packet_binding(),public.research_claim_campaign_binding() from public,anon,authenticated;
create or replace function public.research_finish_idea_run(p_study uuid,p_actor uuid,p_id uuid,p_status text,p_reason text,p_raw text,p_output jsonb,p_usage jsonb,p_provenance jsonb,p_messages jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare prior public.research_idea_runs; result public.research_idea_runs; registration public.research_idea_sessions; begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0)); perform public.research_idea_owner(p_study,p_actor);
 select * into strict prior from public.research_idea_runs where id=p_id and study_id=p_study and actor_id=p_actor for update;
 if p_status not in ('complete','invalid-output','failed') or (p_status<>'complete' and coalesce(btrim(p_reason),'')='') then raise exception 'Run completion needs a status and failure reason'; end if;
 if prior.status<>'running' then
  if prior.status<>p_status or prior.raw_response is distinct from p_raw or prior.output is distinct from p_output then raise exception 'Model attempt is already terminal; preserve it'; end if;
  return to_jsonb(prior);
 end if;
 if p_raw is not null and octet_length(p_raw)>32000 then raise exception 'Model output exceeds retained output budget'; end if;
 if p_status='complete' and (jsonb_typeof(p_output) is distinct from 'object' or p_raw is null) then raise exception 'Completed model call needs original output and parsed data'; end if;
 if p_messages is not null then
  if prior.task<>'planning' or jsonb_typeof(p_messages) is distinct from 'array' or jsonb_array_length(p_messages)>24 or octet_length(p_messages::text)>24000 then raise exception 'Invalid bounded planning history'; end if;
  select * into strict registration from public.research_idea_sessions where session_id=prior.session_id and study_id=p_study and actor_id=p_actor;
  perform public.save_agent_turn(prior.session_id,registration.user_id,p_messages,p_id,prior.prompt_version_id,prior.model_id,(case when exists(select 1 from public.research_claim_designs where study_id=p_study) then 'claim-experiment-design-v1' else 'research-ideas-v1' end),p_raw,(case when exists(select 1 from public.research_claim_designs where study_id=p_study) then 'research-claim-design' else 'research-verification' end),p_usage->'tokens',null,null,p_provenance);
 end if;
 update public.research_idea_runs set status=p_status,reason=p_reason,raw_response=p_raw,
  response_sha256=case when p_raw is null then null else encode(sha256(convert_to(p_raw,'UTF8')),'hex') end,
  output=p_output,usage=p_usage,provenance=prior.provenance||p_provenance,ended_at=clock_timestamp() where id=p_id returning * into result;
 return to_jsonb(result);
end $$;
notify pgrst,'reload schema';
commit;
