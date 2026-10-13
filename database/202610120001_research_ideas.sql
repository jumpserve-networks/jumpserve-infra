begin;

alter table public.research_studies add column study_kind text not null default 'paper' check(study_kind in ('paper','idea'));
alter table public.research_studies alter column paper_url drop not null;
alter table public.research_studies add check((study_kind='paper' and paper_url is not null and paper_url ~ '^https://[^[:space:]]+$') or (study_kind='idea' and paper_url is null));

create or replace function public.research_create_study(p_actor uuid,p_id uuid,p_document jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare existing public.research_studies; kind text=coalesce(p_document->>'study_kind','paper'); expected jsonb; begin
 perform pg_advisory_xact_lock(hashtextextended(p_id::text,0));
 if kind not in ('paper','idea') or (kind='idea' and p_document->>'paper_url' is not null) or
  (kind='paper' and coalesce(p_document->>'paper_url','') !~ '^https://[^[:space:]]+$') then raise exception 'Invalid paper or unpublished-idea origin'; end if;
 expected=p_document||jsonb_build_object('study_kind',kind);
 select * into existing from public.research_studies where id=p_id;
 if found then
  if not exists(select 1 from public.research_study_owners where study_id=p_id and owner_id=p_actor) then raise exception 'Study not found'; end if;
  if (to_jsonb(existing)-'created_at'-'id') is distinct from expected then raise exception 'Request ID already used for different study details'; end if;
  return to_jsonb(existing);
 end if;
 insert into public.research_studies(id,title,paper_url,domain,scope,origin_module,study_kind)
 values(p_id,p_document->>'title',p_document->>'paper_url',p_document->>'domain',p_document->>'scope',p_document->>'origin_module',kind) returning * into existing;
 insert into public.research_study_owners values(p_id,p_actor);
 insert into public.research_audit_events(study_id,actor_id,action,details) values(p_id,p_actor,'intake',jsonb_build_object('request_id',p_id,'study_kind',kind));
 return to_jsonb(existing);
end $$;

create table public.research_idea_packets (
 id uuid primary key, study_id uuid not null references public.research_studies(id),
 version integer not null check(version>0), supersedes_id uuid, document jsonb not null check(jsonb_typeof(document)='object'),
 raw_document text not null check(octet_length(raw_document)<=24000), sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'),
 reason text not null check(length(btrim(reason)) between 1 and 2000), created_at timestamptz not null default clock_timestamp(),
 unique(study_id,id), unique(study_id,version),
 foreign key(study_id,supersedes_id) references public.research_idea_packets(study_id,id),
 check(document=raw_document::jsonb), check(sha256=encode(sha256(convert_to(raw_document,'UTF8')),'hex'))
);
create table public.research_idea_sessions (
 session_id uuid primary key references public.agent_sessions(id), study_id uuid not null references public.research_studies(id),
 actor_id uuid not null, user_id text not null, created_at timestamptz not null default clock_timestamp()
);
create table public.research_idea_runs (
 id uuid primary key, study_id uuid not null, packet_id uuid not null,
 task text not null check(task in ('planning','comprehension','critic')), session_id uuid references public.agent_sessions(id),
 status text not null check(status in ('running','complete','invalid-output','failed')), reason text,
 prompt_version_id uuid not null references public.agent_prompt_versions(id), model_id text not null,
 output jsonb, raw_response text, response_sha256 text, usage jsonb, provenance jsonb not null, request jsonb not null,
 actor_id uuid not null, created_at timestamptz not null default clock_timestamp(), ended_at timestamptz,
 unique(study_id,id), foreign key(study_id,packet_id) references public.research_idea_packets(study_id,id),
 check((task='planning' and session_id is not null) or (task<>'planning' and session_id is null)),
 check((raw_response is null and response_sha256 is null) or response_sha256=encode(sha256(convert_to(raw_response,'UTF8')),'hex'))
);
create unique index research_idea_active_session on public.research_idea_runs(session_id) where session_id is not null and status='running';
create table public.research_idea_readiness (
 id uuid primary key, study_id uuid not null, packet_id uuid not null, packet_sha256 text not null,
 comprehension_run_id uuid not null, critic_run_id uuid not null, decision text not null check(decision='ready'),
 reason text not null check(length(btrim(reason)) between 1 and 2000), actor_id uuid not null, created_at timestamptz not null default clock_timestamp(),
 foreign key(study_id,packet_id) references public.research_idea_packets(study_id,id),
 foreign key(study_id,comprehension_run_id) references public.research_idea_runs(study_id,id),
 foreign key(study_id,critic_run_id) references public.research_idea_runs(study_id,id)
);
create table public.research_idea_campaign_links (
 id uuid primary key, study_id uuid not null, packet_id uuid not null, campaign_id uuid not null, protocol_id uuid not null,
 request jsonb not null, created_at timestamptz not null default clock_timestamp(),
 foreign key(study_id,packet_id) references public.research_idea_packets(study_id,id),
 foreign key(study_id,campaign_id) references public.research_campaigns(study_id,id),
 foreign key(study_id,protocol_id) references public.research_protocols(study_id,id)
);
do $$ declare relation text; begin
 foreach relation in array array['research_idea_packets','research_idea_sessions','research_idea_runs','research_idea_readiness','research_idea_campaign_links'] loop
  execute format('alter table public.%I enable row level security',relation);
  execute format('revoke all on public.%I from public,anon,authenticated',relation);
  execute format('grant select,insert,update on public.%I to service_role',relation);
  if relation<>'research_idea_runs' then
   execute format('create trigger research_idea_immutable before update or delete on public.%I for each row execute function public.research_immutable()',relation);
  end if;
 end loop;
end $$;

-- These helpers and all privileged RPCs are server-only. Browser identities
-- cannot turn a caller-supplied actor into authority.
create function public.research_idea_owner(p_study uuid,p_actor uuid) returns void
language plpgsql security definer set search_path='' as $$ begin
 if not exists(select 1 from public.research_studies s join public.research_study_owners o on o.study_id=s.id
  where s.id=p_study and s.study_kind='idea' and o.owner_id=p_actor) then raise exception 'Idea study not found'; end if;
end $$;

create function public.research_save_idea_packet(p_study uuid,p_actor uuid,p_id uuid,p_previous uuid,p_document jsonb,p_raw text,p_sha256 text,p_reason text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare prior public.research_idea_packets; latest public.research_idea_packets; begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0)); perform public.research_idea_owner(p_study,p_actor);
 select * into prior from public.research_idea_packets where id=p_id;
 if found then
  if prior.study_id<>p_study or prior.document is distinct from p_document or prior.supersedes_id is distinct from p_previous or prior.reason<>p_reason
   or prior.raw_document<>p_raw or prior.sha256<>p_sha256 then raise exception 'Packet request ID already identifies different bytes'; end if;
  return to_jsonb(prior);
 end if;
 select * into latest from public.research_idea_packets where study_id=p_study order by version desc limit 1;
 if latest.id is distinct from p_previous then raise exception 'Draft changed; reload before saving a new version'; end if;
 if latest.document is not distinct from p_document then raise exception 'New packet versions need a changed plan; a new review attempt cannot reset its budget with identical content'; end if;
 if coalesce(latest.version,0)>=100 then raise exception 'Idea revision budget exhausted'; end if;
 insert into public.research_idea_packets values(p_id,p_study,coalesce(latest.version,0)+1,p_previous,p_document,p_raw,p_sha256,p_reason,clock_timestamp()) returning * into prior;
 insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'idea:packet',jsonb_build_object('packet_id',p_id,'sha256',p_sha256));
 return to_jsonb(prior);
end $$;

create function public.research_begin_idea_run(p_study uuid,p_actor uuid,p_user text,p_id uuid,p_packet uuid,p_task text,p_session uuid,p_prompt uuid,p_model text,p_request jsonb,p_provenance jsonb)
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
  where s.module_id='research-verification' and v.id=p_prompt and v.module_id=s.module_id and v.published_at is not null) then raise exception 'An evaluated published idea prompt must be active'; end if;
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
    or conversation.module_id<>'research-verification') then raise exception 'Planning conversation belongs to another user, study or module'; end if;
  if conversation.id is null then
   insert into public.agent_sessions(id,user_id,module_id,messages,updated_at) values(p_session,p_user,'research-verification','[]'::jsonb,clock_timestamp());
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

create function public.research_finish_idea_run(p_study uuid,p_actor uuid,p_id uuid,p_status text,p_reason text,p_raw text,p_output jsonb,p_usage jsonb,p_provenance jsonb,p_messages jsonb)
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
  perform public.save_agent_turn(prior.session_id,registration.user_id,p_messages,p_id,prior.prompt_version_id,prior.model_id,'research-ideas-v1',p_raw,'research-verification',p_usage->'tokens',null,null,p_provenance);
 end if;
 update public.research_idea_runs set status=p_status,reason=p_reason,raw_response=p_raw,
  response_sha256=case when p_raw is null then null else encode(sha256(convert_to(p_raw,'UTF8')),'hex') end,
  output=p_output,usage=p_usage,provenance=prior.provenance||p_provenance,ended_at=clock_timestamp() where id=p_id returning * into result;
 return to_jsonb(result);
end $$;

create function public.research_accept_idea_plan(p_study uuid,p_actor uuid,p_id uuid,p_packet uuid,p_comprehension uuid,p_critic uuid,p_reason text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare proposal public.research_idea_packets; result public.research_idea_readiness; review public.research_idea_runs; selected uuid; field text; begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0)); perform public.research_idea_owner(p_study,p_actor);
 select * into result from public.research_idea_readiness where id=p_id;
 if found then
  if result.study_id<>p_study or result.packet_id<>p_packet or result.comprehension_run_id<>p_comprehension or result.critic_run_id<>p_critic or result.reason<>p_reason then raise exception 'Readiness request ID reused'; end if;
  return to_jsonb(result);
 end if;
 select * into strict proposal from public.research_idea_packets where study_id=p_study order by version desc limit 1;
 if proposal.id<>p_packet then raise exception 'Reviews must cover the current packet'; end if;
 foreach field in array array['problem','question','hypothesis','conditions','related_work','alternatives','design','metrics','controls','falsification','inputs','limitations'] loop
  if coalesce(btrim(proposal.document->>field),'')='' then raise exception 'Plan remains incomplete: %',field; end if;
 end loop;
 if jsonb_typeof(proposal.document->'protocol') is distinct from 'object' then raise exception 'A candidate scientific protocol is required'; end if;
 foreach selected in array array[p_comprehension,p_critic] loop
  select * into strict review from public.research_idea_runs where id=selected and study_id=p_study and packet_id=p_packet;
  if selected is distinct from (select id from public.research_idea_runs where study_id=p_study and packet_id=p_packet and task=review.task order by created_at desc,id desc limit 1) then raise exception 'Use the latest review attempt for each task; do not select an earlier favorable recommendation'; end if;
  if review.task<>(case when selected=p_comprehension then 'comprehension' else 'critic' end) or review.status<>'complete' or review.output->>'verdict' is distinct from 'ready' or
   review.provenance->>'packet_sha256' is distinct from proposal.sha256 or review.provenance->>'context_policy' is distinct from 'fresh-packet-only' or review.provenance->'history_messages' is distinct from '0'::jsonb or
   jsonb_typeof(review.output->'questions') is distinct from 'array' or jsonb_array_length(review.output->'questions')<>0 or
   jsonb_typeof(review.output->'findings') is distinct from 'array' or exists(select 1 from jsonb_array_elements(review.output->'findings') f where f->>'severity'='blocking') then raise exception 'Two complete fresh reviews without blocking findings are required'; end if;
 end loop;
 insert into public.research_idea_readiness values(p_id,p_study,p_packet,proposal.sha256,p_comprehension,p_critic,'ready',p_reason,p_actor,clock_timestamp()) returning * into result;
 return to_jsonb(result);
end $$;

create function public.research_idea_ready(p_study uuid,p_packet uuid,p_sha256 text) returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.research_idea_readiness d where d.study_id=p_study and d.packet_id=p_packet and d.packet_sha256=p_sha256
  and d.comprehension_run_id=(select id from public.research_idea_runs where study_id=p_study and packet_id=p_packet and task='comprehension' order by created_at desc,id desc limit 1)
  and d.critic_run_id=(select id from public.research_idea_runs where study_id=p_study and packet_id=p_packet and task='critic' order by created_at desc,id desc limit 1));
$$;
revoke all on function public.research_idea_ready(uuid,uuid,text) from public,anon,authenticated;
grant execute on function public.research_idea_ready(uuid,uuid,text) to service_role;

create function public.research_guard_idea_protocol() returns trigger language plpgsql set search_path='' as $$
declare proposal public.research_idea_packets; begin
 if (select study_kind from public.research_studies where id=new.study_id)<>'idea' then return new; end if;
 select * into strict proposal from public.research_idea_packets where study_id=new.study_id order by version desc limit 1;
 if new.document->>'idea_packet_id' is distinct from proposal.id::text or new.document->>'idea_packet_sha256' is distinct from proposal.sha256 or
  not public.research_idea_ready(new.study_id,proposal.id,proposal.sha256) or
  (new.document-'idea_packet_id'-'idea_packet_sha256') is distinct from proposal.document->'protocol' then raise exception 'Freeze the reviewed current candidate protocol; material changes require another packet and reviews'; end if;
 return new;
end $$;
create trigger research_idea_protocol_gate before insert on public.research_protocols for each row execute function public.research_guard_idea_protocol();

create function public.research_prepare_idea_campaign(p_study uuid,p_actor uuid,p_id uuid,p_packet uuid,p_request jsonb,p_records jsonb,p_campaign uuid,p_protocol uuid)
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
  not exists(select 1 from public.research_campaigns where study_id=p_study and id=p_campaign and protocol_id=p_protocol and adapter='domain-operator') or
  not exists(select 1 from public.research_claim_checks where study_id=p_study and campaign_id=p_campaign and applicability='applicable') then raise exception 'Prepared campaign needs its reviewed protocol and explicit hypothesis link'; end if;
 insert into public.research_idea_campaign_links values(p_id,p_study,p_packet,p_campaign,p_protocol,p_request,clock_timestamp()) returning * into result;
 return to_jsonb(result);
end $$;

create function public.research_guard_idea_queue() returns trigger language plpgsql set search_path='' as $$
declare proposal public.research_idea_packets; protocol public.research_protocols; begin
 if (select study_kind from public.research_studies where id=new.study_id)<>'idea' then return new; end if;
 select * into strict proposal from public.research_idea_packets where study_id=new.study_id order by version desc limit 1;
 select p.* into strict protocol from public.research_protocols p join public.research_campaigns c on c.protocol_id=p.id and c.study_id=p.study_id where c.id=new.campaign_id and c.study_id=new.study_id;
 if protocol.document->>'idea_packet_id' is distinct from proposal.id::text or not public.research_idea_ready(new.study_id,proposal.id,proposal.sha256) then raise exception 'Current idea packet readiness is required for a new queue job'; end if;
 return new;
end $$;
create trigger research_idea_queue_gate before insert on public.research_queue_jobs for each row execute function public.research_guard_idea_queue();

-- Keep immutable terminal attempts and prompt/context identity even though a
-- running attempt must accept its server-side completion.
create function public.research_protect_idea_run() returns trigger language plpgsql set search_path='' as $$ begin
 if tg_op='DELETE' or old.status<>'running' or
  (new.provenance-array['stop_reason','tool_events','data_origin','provider_message','raw_response_scope']) is distinct from
  (old.provenance-array['stop_reason','tool_events','data_origin','provider_message','raw_response_scope']) or
  (to_jsonb(new)-array['status','reason','output','raw_response','response_sha256','usage','provenance','ended_at']) is distinct from
  (to_jsonb(old)-array['status','reason','output','raw_response','response_sha256','usage','provenance','ended_at']) then raise exception 'Original model attempt and terminal results are immutable'; end if;
 return new;
end $$;
create trigger research_idea_run_protection before update or delete on public.research_idea_runs for each row execute function public.research_protect_idea_run();

revoke all on function public.research_idea_owner(uuid,uuid),public.research_save_idea_packet(uuid,uuid,uuid,uuid,jsonb,text,text,text),
 public.research_begin_idea_run(uuid,uuid,text,uuid,uuid,text,uuid,uuid,text,jsonb,jsonb),public.research_finish_idea_run(uuid,uuid,uuid,text,text,text,jsonb,jsonb,jsonb,jsonb),
 public.research_accept_idea_plan(uuid,uuid,uuid,uuid,uuid,uuid,text),public.research_prepare_idea_campaign(uuid,uuid,uuid,uuid,jsonb,jsonb,uuid,uuid),
 public.research_guard_idea_protocol(),public.research_guard_idea_queue(),public.research_protect_idea_run() from public,anon,authenticated;
grant execute on function public.research_save_idea_packet(uuid,uuid,uuid,uuid,jsonb,text,text,text),
 public.research_begin_idea_run(uuid,uuid,text,uuid,uuid,text,uuid,uuid,text,jsonb,jsonb),public.research_finish_idea_run(uuid,uuid,uuid,text,text,text,jsonb,jsonb,jsonb,jsonb),
 public.research_accept_idea_plan(uuid,uuid,uuid,uuid,uuid,uuid,text),public.research_prepare_idea_campaign(uuid,uuid,uuid,uuid,jsonb,jsonb,uuid,uuid) to service_role;
notify pgrst,'reload schema';
commit;
