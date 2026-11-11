begin;

-- Phase one is owned by Next.js and the OpenAI Responses API. These rows do
-- not create autonomy tasks, queue jobs, or worker dispatches.
create table public.research_paper_intakes (
 study_id uuid primary key references public.research_studies(id), owner_id uuid not null,
 filename text not null, sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'),
 byte_count integer not null check(byte_count between 1 and 10000000),
 source_id uuid not null default gen_random_uuid(), original_artifact_id uuid not null default gen_random_uuid(),
 text_artifact_id uuid not null default gen_random_uuid(),
 status text not null default 'uploaded' check(status in ('uploaded','submitting','processing','ready','failed','uncertain','cancelled')),
 submit_token uuid, provider_response_id text unique, model_id text, request jsonb, response jsonb,
 paper_text jsonb, breakdown jsonb, title text, domain text, authors jsonb not null default '[]',
 reason text, reserved_cents integer not null default 0 check(reserved_cents>=0),
 model_calls integer not null default 0 check(model_calls between 0 and 1), policy_snapshot jsonb,
 created_at timestamptz not null default clock_timestamp(),updated_at timestamptz not null default clock_timestamp(),
 deadline_at timestamptz not null default clock_timestamp()+interval '7 days', revision integer not null default 1,
 check(jsonb_typeof(authors)='array'),check(status<>'ready' or breakdown is not null),
 check(provider_response_id is null or provider_response_id ~ '^resp_[A-Za-z0-9_-]{1,200}$')
);
create table public.research_paper_intake_events (
 id bigint generated always as identity primary key,study_id uuid not null references public.research_paper_intakes(study_id),
 revision integer not null,snapshot jsonb not null,created_at timestamptz not null default clock_timestamp(),unique(study_id,revision)
);
create function public.research_paper_intake_history() returns trigger language plpgsql set search_path='' as $$begin
 if tg_op='DELETE' then raise exception 'Retain phase-one paper history';end if;
 if tg_op='UPDATE' then
  if (new.study_id,new.owner_id,new.filename,new.sha256,new.byte_count,new.source_id,new.original_artifact_id,new.text_artifact_id,new.created_at,new.deadline_at)
   is distinct from (old.study_id,old.owner_id,old.filename,old.sha256,old.byte_count,old.source_id,old.original_artifact_id,old.text_artifact_id,old.created_at,old.deadline_at)
   or old.status in ('ready','cancelled') or new.model_calls<old.model_calls or new.reserved_cents<old.reserved_cents
   or old.provider_response_id is not null and new.provider_response_id is distinct from old.provider_response_id
   or old.request is not null and new.request is distinct from old.request
  then raise exception 'Original phase-one identity, evidence, limits and provider call are immutable';end if;
  new.revision=old.revision+1;new.updated_at=clock_timestamp();
 end if;
 return new;
end$$;
create trigger paper_intake_history before insert or update or delete on public.research_paper_intakes for each row execute function public.research_paper_intake_history();
create function public.research_paper_intake_audit() returns trigger language plpgsql set search_path='' as $$begin
 insert into public.research_paper_intake_events(study_id,revision,snapshot) values(new.study_id,new.revision,to_jsonb(new));return new;end$$;
create trigger paper_intake_audit after insert or update on public.research_paper_intakes for each row execute function public.research_paper_intake_audit();
create trigger paper_intake_events_immutable before update or delete on public.research_paper_intake_events for each row execute function public.research_immutable();
alter table public.research_paper_intakes enable row level security;
alter table public.research_paper_intake_events enable row level security;
revoke all on public.research_paper_intakes,public.research_paper_intake_events from public,anon,authenticated,service_role;
grant select on public.research_paper_intakes,public.research_paper_intake_events to service_role;

create function public.research_paper_intake(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare i public.research_paper_intakes;u public.research_paper_uploads;r public.research_paper_reviews;
 s public.research_studies;w public.research_autonomy_workflows;v jsonb;meta jsonb;admitted boolean=false;
 spent bigint=0;calls bigint=0;policy jsonb;token uuid;begin
 if p_actor is null or p_study is null or jsonb_typeof(p_payload) is distinct from 'object' then raise exception 'Verified paper owner and explicit operation required';end if;
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into i from public.research_paper_intakes where study_id=p_study for update;
 if p_operation='reserve' then
  if (select count(*) from jsonb_object_keys(p_payload))<>3 or
   jsonb_typeof(p_payload->'filename') is distinct from 'string' or length(p_payload->>'filename') not between 5 and 200 or
   lower(right(p_payload->>'filename',4))<>'.pdf' or p_payload->>'filename' ~ '[/\\[:cntrl:]]' or
   coalesce(p_payload->>'sha256','') !~ '^[a-f0-9]{64}$' or jsonb_typeof(p_payload->'byte_count') is distinct from 'number' or
   (p_payload->>'byte_count')::numeric<>trunc((p_payload->>'byte_count')::numeric) or (p_payload->>'byte_count')::numeric not between 1 and 10000000
  then raise exception 'Supply a bounded original PDF identity';end if;
  if i.study_id is not null then
   if (i.owner_id,i.filename,i.sha256,i.byte_count) is distinct from (p_actor,p_payload->>'filename',p_payload->>'sha256',(p_payload->>'byte_count')::integer) then raise exception 'Paper reservation identity conflicts';end if;
   return to_jsonb(i);
  end if;
  if (select count(*) from public.research_paper_intakes where owner_id=p_actor and status in ('uploaded','submitting','processing','uncertain') and deadline_at>clock_timestamp())>=10 then raise exception 'Finish an existing paper before adding more pending uploads';end if;
  select * into s from public.research_studies where id=p_study;
  select * into u from public.research_paper_uploads where id=p_study;
  if s.id is not null then
   if s.study_kind<>'paper' or u.id is null or u.owner_id<>p_actor or
    not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) or
    u.paper->'paper_upload' is distinct from p_payload or exists(select 1 from public.research_paper_reviews where study_id=p_study and status='confirmed')
   then raise exception 'Only the owner can resume an unconfirmed uploaded paper';end if;
   if exists(select 1 from public.research_autonomy_tasks where study_id=p_study and status='running' and lease_until>clock_timestamp()) or
    exists(select 1 from public.research_model_dispatches where study_id=p_study and status in ('queued','running','unknown')) or
    exists(select 1 from public.research_autonomy_turns where study_id=p_study and status in ('running','unknown'))
   then raise exception 'Reconcile the original intake call before changing its execution path';end if;
   if exists(select 1 from public.research_autonomy_workflows where study_id=p_study) then perform public.research_autonomy_control('cancel',p_actor,p_study,'{}');end if;
  else
   if u.id is not null then raise exception 'This identity already belongs to another original upload';end if;
   meta=jsonb_build_object('title',left(p_payload->>'filename',300),'paper_url',null,'paper_upload',p_payload,'domain','Paper breakdown','scope','Phase one: organize the original paper into Access, Experiment, Data and Validate. No experiments authorized.','study_kind','paper','origin_module',null);
   insert into public.research_paper_uploads(id,owner_id,paper) values(p_study,p_actor,meta);
   insert into public.research_studies(id,title,paper_url,paper_upload,domain,scope,origin_module,study_kind)
    values(p_study,meta->>'title',null,p_payload,meta->>'domain',meta->>'scope',null,'paper');
   insert into public.research_study_owners(study_id,owner_id) values(p_study,p_actor);
   insert into public.research_paper_reviews(study_id) values(p_study);
   insert into public.research_audit_events(study_id,actor_id,action,details) values(p_study,p_actor,'intake',jsonb_build_object('phase','paper-breakdown','execution','nextjs-openai','worker_dispatches',0));
  end if;
  insert into public.research_paper_intakes(study_id,owner_id,filename,sha256,byte_count,deadline_at)
   values(p_study,p_actor,p_payload->>'filename',p_payload->>'sha256',(p_payload->>'byte_count')::integer,least(clock_timestamp()+interval '7 days',(select deadline_at from public.research_autonomy_workflows where study_id=p_study))) returning * into i;
  return to_jsonb(i);
 end if;
 if i.study_id is null or i.owner_id<>p_actor or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper intake not found';end if;
 if p_operation='begin' then
  if i.status<>'uploaded' then return to_jsonb(i)||jsonb_build_object('admitted',false);end if;
  if i.deadline_at<=clock_timestamp() then raise exception 'The original paper deadline has expired';end if;
  if p_payload->>'model_id' is distinct from 'gpt-5.4-mini-2026-03-17' or
   jsonb_typeof(p_payload->'request') is distinct from 'object' or p_payload->'request'->>'model' is distinct from p_payload->>'model_id' or
   jsonb_typeof(p_payload->'paper_text') is distinct from 'object' or (p_payload->>'reserved_cents')::integer is distinct from 100
   or octet_length((p_payload->'request')::text)>300000 or octet_length((p_payload->'paper_text')::text)>300000
  then raise exception 'Bounded one-pass request and retained paper text required';end if;
  select * into w from public.research_autonomy_workflows where study_id=p_study;
  if found then
   if w.max_spend_cents is not null and w.committed_cents+100>w.max_spend_cents then raise exception 'The original assessment spending limit does not admit this call';end if;
   spent=w.committed_cents;select coalesce(sum(attempts),0) into calls from public.research_autonomy_tasks where study_id=p_study;end if;
  if not public.autonomy_budget_allows('research_assessment',spent+i.reserved_cents,calls+i.model_calls,100,1) then raise exception 'The assessment budget does not admit this model call';end if;
  policy=public.autonomy_assessment_budget_terms();token=gen_random_uuid();
  for v in select value from jsonb_array_elements(p_payload->'artifacts') loop
   if v->>'sha256' !~ '^[a-f0-9]{64}$' or v->>'storage_path'<>p_study::text||'/'||(v->>'sha256') then raise exception 'Verified artifact identity required';end if;
   insert into public.research_artifacts(id,study_id,sha256,byte_count,storage_path,media_type,provenance,verified_at)
    values((v->>'id')::uuid,p_study,v->>'sha256',(v->>'byte_count')::bigint,v->>'storage_path',v->>'media_type',v->'provenance',clock_timestamp());
  end loop;
  if not exists(select 1 from public.research_artifacts where study_id=p_study and id=i.original_artifact_id and sha256=i.sha256 and byte_count=i.byte_count) or
   not exists(select 1 from public.research_artifacts where study_id=p_study and id=i.text_artifact_id) then raise exception 'Original PDF and text artifacts must be retained before inference';end if;
  insert into public.research_sources(id,study_id,citation,kind,role,retrieved_version,sha256,byte_count,access_status,review_status,review_definition,examined,unexamined,retrieval_attempts,reviewer,findings,limitations)
   values(i.source_id,p_study,i.filename,'research','Original owner-uploaded paper','SHA256:'||i.sha256,i.sha256,i.byte_count,'retrieved','partial-review','Phase-one organization of extracted text only.','Recorded PDF text pages.','Figures, equations, scanned content and supplements may be missing.','[]',jsonb_build_object('type','AI','identity',p_payload->>'model_id','independence','Reading aid; independent review not asserted'),'No scientific finding or validation is established.','Extracted text only; no experiments authorized.');
  select * into u from public.research_paper_uploads where id=p_study;
  if u.status='pending' then update public.research_paper_uploads set status='verified' where id=p_study;end if;
  if u.status in ('pending','verified') then update public.research_paper_uploads set status='started',original_artifact_id=i.original_artifact_id where id=p_study;end if;
  update public.research_paper_intakes set status='submitting',submit_token=token,model_id=p_payload->>'model_id',request=p_payload->'request',paper_text=p_payload->'paper_text',reserved_cents=100,model_calls=1,policy_snapshot=policy,reason='Submitting one paper breakdown request.' where study_id=p_study returning * into i;
  return to_jsonb(i)||jsonb_build_object('admitted',true);
 end if;
 if p_operation='submitted' then
  if i.provider_response_id is not null then
   if i.provider_response_id<>p_payload->>'response_id' then raise exception 'Provider identity conflicts with the retained call';end if;return to_jsonb(i);
  end if;
  if i.status not in ('submitting','uncertain') or i.submit_token is distinct from (p_payload->>'token')::uuid or coalesce(p_payload->>'response_id','') !~ '^resp_[A-Za-z0-9_-]{1,200}$' then raise exception 'Original submitting call identity required';end if;
  update public.research_paper_intakes set status='processing',provider_response_id=p_payload->>'response_id',response=p_payload->'response',reason='OpenAI is preparing the four paper sections.' where study_id=p_study returning * into i;
  return to_jsonb(i);
 end if;
 if p_operation in ('uncertain','failed') then
  if p_operation='uncertain' and i.provider_response_id is not null then return to_jsonb(i);end if;
  if i.status not in ('uploaded','submitting','processing','uncertain') or i.submit_token is distinct from (p_payload->>'token')::uuid then raise exception 'Original call token required';end if;
  update public.research_paper_intakes set status=case when p_operation='uncertain' then 'uncertain' else 'failed' end,
   response=coalesce(p_payload->'response',response),reason=left(p_payload->>'reason',2000) where study_id=p_study returning * into i;
  update public.research_paper_reviews set status='failed',reason=i.reason,revision=revision+1,updated_at=clock_timestamp() where study_id=p_study;
  return to_jsonb(i);
 end if;
 if p_operation='finish' then
  if i.status='ready' then return to_jsonb(i);end if;
  if i.status<>'processing' or i.provider_response_id is distinct from p_payload->>'response_id' or
   p_payload->'breakdown'->>'status' is distinct from 'ready' or p_payload->'breakdown'->>'source_id' is distinct from i.source_id::text or
   p_payload->'breakdown'->>'text_artifact_id' is distinct from i.text_artifact_id::text then raise exception 'The retained response and source-bound breakdown are required';end if;
  update public.research_paper_intakes set status='ready',response=p_payload->'response',breakdown=p_payload->'breakdown',
   title=p_payload->>'title',domain=p_payload->>'domain',authors=p_payload->'authors',reason=null where study_id=p_study returning * into i;
  update public.research_paper_reviews set status='ready',title=i.title,domain=i.domain,
   metadata=metadata||jsonb_build_object('breakdown',i.breakdown,'authors',jsonb_build_object('version','paper-authors-v1','names',i.authors,'page',p_payload->'authors_page','method','Source-grounded one-pass OpenAI extraction'),'phase_one','nextjs-openai'),
   revision=revision+1,reason='Four-section paper breakdown ready; no experiments requested.' where study_id=p_study;
  return to_jsonb(i);
 end if;
 if p_operation='cancel' then
  if i.status in ('ready','failed','cancelled') then return to_jsonb(i);end if;
  update public.research_paper_intakes set status='cancelled',response=coalesce(p_payload->'response',response),reason=case when i.status='uncertain' and i.provider_response_id is null then 'Owner stopped local preparation. The original provider outcome remains unknown; a remote call may still finish and incur charges.' else 'Owner cancelled paper preparation. Retained provider identities and evidence are preserved.' end where study_id=p_study returning * into i;
  update public.research_paper_reviews set status='failed',reason=i.reason,revision=revision+1,updated_at=clock_timestamp() where study_id=p_study;
  return to_jsonb(i);
 end if;
 raise exception 'Unknown paper intake operation';
end$$;
revoke all on function public.research_paper_intake(text,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.research_paper_intake(text,uuid,uuid,jsonb) to service_role;
commit;
