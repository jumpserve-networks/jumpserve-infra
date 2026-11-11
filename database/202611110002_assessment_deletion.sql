begin;

-- Logical deletion removes every application/public view while retaining the
-- original scientific evidence, provider identities, measurements and limits.
alter table public.research_studies add column deleted_at timestamptz;

create or replace function public.research_confirm_paper_details() returns trigger language plpgsql set search_path='' as $$ begin
 if tg_op='UPDATE' and old.deleted_at is null and new.deleted_at is not null and
  (to_jsonb(new)-'deleted_at')=(to_jsonb(old)-'deleted_at') then return new;end if;
 if tg_op='UPDATE' and old.deleted_at is null and new.deleted_at is null and
  (to_jsonb(new)-array['title','domain'])=(to_jsonb(old)-array['title','domain']) and
  not exists(select 1 from public.research_publications where study_id=old.id) and
  exists(select 1 from public.research_paper_reviews r join public.research_paper_uploads u on u.id=r.study_id
   where r.study_id=old.id and r.status='confirmed' and old.title=u.paper->>'title' and old.domain=u.paper->>'domain'
    and new.title=r.confirmation->>'title' and new.domain=r.confirmation->>'domain') then return new;end if;
 raise exception 'Assessment evidence is immutable; deleted assessments cannot be restored';
end $$;

create function public.research_assessment_deleted(p_study uuid) returns boolean
language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.research_studies where id=p_study and deleted_at is not null)
$$;
revoke all on function public.research_assessment_deleted(uuid) from public;
grant execute on function public.research_assessment_deleted(uuid) to anon,authenticated,service_role;

-- Serialize new work with deletion. No retained evidence is edited or purged.
create function public.research_require_active_assessment() returns trigger
language plpgsql security definer set search_path='' as $$
declare study uuid;begin
 study=(to_jsonb(new)->>case when tg_table_name in ('research_studies','research_paper_uploads') then 'id' else 'study_id' end)::uuid;
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if public.research_assessment_deleted(study) then raise exception 'Assessment not found' using errcode='P0002';end if;
 return new;
end $$;

do $$declare t record;column_name text;begin
 for t in select c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='public' and c.relkind='r' and (c.relname like 'research\_%' escape '\' or c.relname='platform_assessment_blockers') and (c.relname in ('research_studies','research_paper_uploads') or
   exists(select 1 from pg_attribute a where a.attrelid=c.oid and a.attname='study_id' and a.atttypid='uuid'::regtype and not a.attisdropped)) loop
  execute format('create trigger assessment_active before insert or update on public.%I for each row execute function public.research_require_active_assessment()',t.relname);
  column_name=case when t.relname in ('research_studies','research_paper_uploads') then 'id' else 'study_id' end;
  execute format('create policy assessment_not_deleted on public.%I as restrictive for select to anon,authenticated using(not public.research_assessment_deleted(%I))',t.relname,column_name);
 end loop;
end $$;

create function public.research_delete_assessment(p_actor uuid,p_study uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare s public.research_studies;deleted timestamptz;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into s from public.research_studies where id=p_study for update;
 if p_actor is null or s.id is null or s.study_kind<>'paper' or
  not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) or
  not exists(select 1 from auth.users u join auth.identities i on i.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and i.provider='google')
 then raise exception 'Assessment not found' using errcode='P0002';end if;
 if s.deleted_at is not null then return jsonb_build_object('id',p_study,'deleted',true);end if;
 if exists(select 1 from public.research_paper_intakes where study_id=p_study and
  (status in ('submitting','processing','uncertain') or response->>'status' in ('queued','in_progress','cancelling') or
   model_calls>0 and provider_response_id is null and submit_token is not null and coalesce(response->>'status','') !~ '^[45][0-9]{2}$')) or
  exists(select 1 from public.research_autonomy_workflows where study_id=p_study and status='running') or
  exists(select 1 from public.research_autonomy_tasks where study_id=p_study and status in ('queued','running','waiting')) or
  exists(select 1 from public.research_autonomy_turns where study_id=p_study and status in ('running','unknown')) or
  exists(select 1 from public.research_model_dispatches where study_id=p_study and status in ('queued','running','unknown')) or
  exists(select 1 from public.research_builder_calls where study_id=p_study and status in ('running','unknown')) or
  exists(select 1 from public.research_queue_jobs where study_id=p_study and status in ('queued','manual','running')) or
  exists(select 1 from public.research_network_executions where study_id=p_study and phase in ('pending','dispatching','running'))
 then raise exception 'Stop running work and reconcile pending calls before deleting' using errcode='55000';end if;
 -- An unused upload must release its pending-intake slot without admitting a call.
 if exists(select 1 from public.research_paper_intakes where study_id=p_study and status='uploaded') then
  perform public.research_paper_intake('cancel',p_actor,p_study,'{}');end if;
 deleted=clock_timestamp();
 insert into public.research_audit_events(study_id,actor_id,action,details)
  values(p_study,p_actor,'delete-assessment',jsonb_build_object('deleted_at',deleted,'evidence_retained',true));
 update public.research_studies set deleted_at=deleted where id=p_study;
 return jsonb_build_object('id',p_study,'deleted',true);
end $$;
revoke all on function public.research_delete_assessment(uuid,uuid) from public,anon,authenticated;
grant execute on function public.research_delete_assessment(uuid,uuid) to service_role;

notify pgrst,'reload schema';
commit;
