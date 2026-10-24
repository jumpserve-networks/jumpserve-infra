begin;

-- Preparation shares the paper's original budget/deadline. It authorizes text
-- extraction only; an owner confirmation separately admits claim work.
create table public.research_paper_reviews (
 study_id uuid primary key references public.research_studies(id),
 status text not null default 'preparing' check(status in ('preparing','ready','failed','confirmed')),
 revision integer not null default 1 check(revision>0),
 title text check(length(title) between 1 and 300), domain text check(length(domain) between 1 and 5000),
 metadata jsonb not null default '{}', seeds jsonb not null default '[]',
 coverage jsonb not null default '{}', reason text,
 confirmation jsonb, confirmed_at timestamptz,
 created_at timestamptz not null default clock_timestamp(), updated_at timestamptz not null default clock_timestamp(),
 check(jsonb_typeof(metadata)='object' and jsonb_typeof(seeds)='array' and jsonb_array_length(seeds)<=200),
 check((status='confirmed')=(confirmation is not null and confirmed_at is not null))
);
create table public.research_paper_review_events (
 id uuid primary key default gen_random_uuid(), study_id uuid not null references public.research_paper_reviews(study_id),
 revision integer not null, snapshot jsonb not null, created_at timestamptz not null default clock_timestamp(), unique(study_id,revision)
);
create trigger research_paper_review_history_immutable before update or delete on public.research_paper_review_events
 for each row execute function public.research_immutable();
create function public.research_paper_review_history() returns trigger language plpgsql set search_path='' as $$ begin
 if tg_op='DELETE' or (tg_op='UPDATE' and (old.status='confirmed' or new.study_id<>old.study_id or new.created_at<>old.created_at or new.revision<>old.revision+1)) then
  raise exception 'Preserve paper review identity, revisions and confirmed information';
 end if;
 insert into public.research_paper_review_events(study_id,revision,snapshot) values(new.study_id,new.revision,to_jsonb(new));
 return new;
end $$;
create trigger research_paper_review_history after insert or update on public.research_paper_reviews
 for each row execute function public.research_paper_review_history();
create trigger research_paper_review_no_delete before delete on public.research_paper_reviews
 for each row execute function public.research_paper_review_history();
alter table public.research_paper_reviews enable row level security;
alter table public.research_paper_review_events enable row level security;
revoke all on public.research_paper_reviews,public.research_paper_review_events from public,anon,authenticated;
grant select,insert,update on public.research_paper_reviews to service_role;
grant select on public.research_paper_review_events to service_role;

-- The uploaded draft's filename/domain placeholders may be replaced exactly
-- once by its confirmed metadata. Original upload JSON, initial prompt, review
-- revisions and scientific evidence remain immutable. Historical/published
-- assessments retain the original append-only rule.
create function public.research_confirm_paper_details() returns trigger language plpgsql set search_path='' as $$ begin
 if tg_op='UPDATE' and (to_jsonb(new)-array['title','domain'])=(to_jsonb(old)-array['title','domain']) and
  not exists(select 1 from public.research_publications where study_id=old.id) and
  exists(select 1 from public.research_paper_reviews r join public.research_paper_uploads u on u.id=r.study_id
   where r.study_id=old.id and r.status='confirmed' and old.title=u.paper->>'title' and old.domain=u.paper->>'domain'
    and new.title=r.confirmation->>'title' and new.domain=r.confirmation->>'domain') then return new;
 end if;
 raise exception 'Assessment records are immutable except for confirmed uploaded-draft metadata';
end $$;
drop trigger research_append_only on public.research_studies;
create trigger research_append_only before update or delete on public.research_studies for each row execute function public.research_confirm_paper_details();

alter function public.research_paper_upload(text,uuid,uuid,jsonb) rename to research_paper_upload_before_confirmation;
create function public.research_paper_upload(p_operation text,p_actor uuid,p_id uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$ declare result jsonb; begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_operation='prepare' then
  result=public.research_paper_upload_before_confirmation('start',p_actor,p_id,p_payload);
  insert into public.research_paper_reviews(study_id) values(p_id) on conflict do nothing;
  return result;
 end if;
 return public.research_paper_upload_before_confirmation(p_operation,p_actor,p_id,p_payload);
end $$;

-- Fence every entry point, including ordinary/manual queue submissions. The
-- advisory lock gives inserts and confirmation the same serialization order.
create function public.research_require_paper_confirmation() returns trigger language plpgsql set search_path='' as $$ begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if exists(select 1 from public.research_paper_reviews where study_id=new.study_id and status<>'confirmed') and
  (tg_table_name='research_queue_jobs' or to_jsonb(new)->>'claim_id' is not null) then
  raise exception 'Review the extracted paper information and confirm before starting claim work';
 end if;
 return new;
end $$;
create trigger research_paper_confirmation_tasks before insert on public.research_autonomy_tasks
 for each row execute function public.research_require_paper_confirmation();
create trigger research_paper_confirmation_queue before insert on public.research_queue_jobs
 for each row execute function public.research_require_paper_confirmation();

alter function public.research_autonomy_control(text,uuid,uuid,jsonb) rename to research_autonomy_before_confirmation;
create function public.research_autonomy_control(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.research_paper_reviews; t public.research_autonomy_tasks; result jsonb; v_seeds jsonb; begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into r from public.research_paper_reviews where study_id=p_study for update;
 if r.study_id is not null and r.status<>'confirmed' and p_operation='seed' then
  if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper review required'; end if;
  select * into strict t from public.research_autonomy_tasks where study_id=p_study and id=(p_payload->>'task_id')::uuid and claim_id is null;
  if t.status<>'running' or t.lease_token is distinct from (p_payload->>'token')::uuid or t.lease_until<=clock_timestamp() or r.status<>'preparing' then raise exception 'Current preparation lease required'; end if;
  if jsonb_typeof(p_payload->'claims') is distinct from 'array' then raise exception 'Candidate inventory required'; end if;
  if exists(select 1 from jsonb_array_elements(p_payload->'claims') v where not exists(select 1 from public.research_claims c where c.study_id=p_study and c.id=(v->>'claim_id')::uuid)) then raise exception 'Retained claim identity required'; end if;
  select coalesce(jsonb_agg(v order by v->>'claim_id'),'[]') into v_seeds from (select distinct on (v->>'claim_id') v from jsonb_array_elements(r.seeds||(p_payload->'claims')) v order by v->>'claim_id') x;
  if jsonb_array_length(v_seeds)>200 then raise exception 'Candidate inventory exceeds 200 claims'; end if;
  update public.research_paper_reviews set seeds=v_seeds,revision=revision+1,updated_at=clock_timestamp() where study_id=p_study;
  return jsonb_build_object('seeded',false,'awaiting_confirmation',true);
 end if;
 result=public.research_autonomy_before_confirmation(p_operation,p_actor,p_study,p_payload);
 if r.study_id is not null and r.status='preparing' and p_operation='advance' then
  select * into strict t from public.research_autonomy_tasks where id=(p_payload->>'task_id')::uuid and study_id=p_study;
  if t.claim_id is null and t.status in ('finished','blocked','budget','deadline','cancelled') then
   update public.research_paper_reviews set status=case when t.status='finished' and jsonb_array_length(seeds)>0 then 'ready' else 'failed' end,
    reason=t.reason,coverage=t.context,revision=revision+1,updated_at=clock_timestamp() where study_id=p_study;
  end if;
 end if;
 return result;
end $$;

create function public.research_paper_review(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r public.research_paper_reviews; w public.research_autonomy_workflows; t public.research_autonomy_tasks;
 selected jsonb; v_confirmation jsonb; result jsonb; begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_actor is null or not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper review not found'; end if;
 select * into strict r from public.research_paper_reviews where study_id=p_study for update;
 if p_operation='metadata' then
  select * into strict t from public.research_autonomy_tasks where id=(p_payload->>'task_id')::uuid and study_id=p_study and claim_id is null;
  if r.status<>'preparing' or t.status<>'running' or t.lease_token is distinct from (p_payload->>'token')::uuid or t.lease_until<=clock_timestamp() then raise exception 'Current preparation lease required'; end if;
  update public.research_paper_reviews set title=coalesce(nullif(p_payload->>'title',''),title),domain=coalesce(nullif(p_payload->>'domain',''),domain),
   metadata=metadata||(p_payload->'metadata'),revision=revision+1,updated_at=clock_timestamp() where study_id=p_study returning * into r;
  return to_jsonb(r);
 end if;
 if p_operation<>'confirm' then raise exception 'Unknown paper review operation'; end if;
 if jsonb_typeof(p_payload->'claim_ids') is distinct from 'array' or jsonb_array_length(p_payload->'claim_ids') not between 1 and 200 or
  length(btrim(coalesce(p_payload->>'title',''))) not between 1 and 300 or length(btrim(coalesce(p_payload->>'domain',''))) not between 1 and 5000 then raise exception 'Confirm a title, research domain and at least one extracted claim'; end if;
 select jsonb_agg(value order by value) into selected from (select distinct value from jsonb_array_elements_text(p_payload->'claim_ids')) x;
 v_confirmation=jsonb_build_object('title',btrim(p_payload->>'title'),'domain',btrim(p_payload->>'domain'),'claim_ids',selected,'review_revision',p_payload->'revision','confirmed_by',p_actor);
 if r.status='confirmed' then
  if r.confirmation is distinct from v_confirmation then raise exception 'This paper review was already confirmed with different information'; end if;
  return to_jsonb(r);
 end if;
 if r.status<>'ready' or r.revision is distinct from (p_payload->>'revision')::integer then raise exception 'Paper preparation changed or is incomplete; reload the review'; end if;
 select * into strict w from public.research_autonomy_workflows where study_id=p_study for update;
 if w.status in ('cancelled','budget','deadline') or w.deadline_at<=clock_timestamp()+interval '180 seconds' or w.committed_cents+5>w.max_spend_cents then raise exception 'Original paper authorization cannot admit more work'; end if;
 if exists(select 1 from jsonb_array_elements_text(selected) c where not exists(select 1 from jsonb_array_elements(r.seeds) s where s->>'claim_id'=c)) then raise exception 'Select only extracted claims from this paper review'; end if;
 update public.research_paper_reviews set status='confirmed',confirmation=v_confirmation,confirmed_at=clock_timestamp(),revision=revision+1,updated_at=clock_timestamp() where study_id=p_study returning * into r;
 update public.research_studies set title=v_confirmation->>'title',domain=v_confirmation->>'domain' where id=p_study;
 update public.research_autonomy_workflows set status='running',reason='Owner confirmed paper information; selected claims are ready for assessment.',updated_at=clock_timestamp() where study_id=p_study;
 select jsonb_agg(s) into selected from jsonb_array_elements(r.seeds) s where v_confirmation->'claim_ids' ? (s->>'claim_id');
 result=public.research_autonomy_control('seed',p_actor,p_study,jsonb_build_object('claims',selected));
 return to_jsonb(r);
end $$;
revoke all on function public.research_paper_upload_before_confirmation(text,uuid,uuid,jsonb),public.research_autonomy_before_confirmation(text,uuid,uuid,jsonb),
 public.research_paper_review_history(),public.research_confirm_paper_details(),public.research_require_paper_confirmation(),public.research_paper_upload(text,uuid,uuid,jsonb),
 public.research_autonomy_control(text,uuid,uuid,jsonb),public.research_paper_review(text,uuid,uuid,jsonb) from public,anon,authenticated;
revoke all on function public.research_paper_upload_before_confirmation(text,uuid,uuid,jsonb),public.research_autonomy_before_confirmation(text,uuid,uuid,jsonb) from service_role;
grant execute on function public.research_paper_upload(text,uuid,uuid,jsonb),public.research_autonomy_control(text,uuid,uuid,jsonb),public.research_paper_review(text,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
