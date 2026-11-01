begin;

-- A pristine queued admission is not an unknown provider outcome. Account for
-- it only while its terminal parent and the original claim row are locked.
create table public.research_queued_dispatch_reconciliations (
 dispatch_id uuid primary key references public.research_model_dispatches(id),
 study_id uuid not null,task_id uuid not null,request_sha256 text not null,
 snapshot_raw text not null,snapshot_sha256 text not null,
 parent_turn_status text not null check(parent_turn_status in ('failed','unknown','invalid-output')),
 proof jsonb not null,created_at timestamptz not null default clock_timestamp(),
 check(octet_length(snapshot_raw)<=1100000),
 check(snapshot_sha256=encode(sha256(convert_to(snapshot_raw,'UTF8')),'hex')),
 foreign key(study_id,task_id) references public.research_autonomy_tasks(study_id,id)
);
alter table public.research_queued_dispatch_reconciliations enable row level security;
revoke all on public.research_queued_dispatch_reconciliations from public,anon,authenticated,service_role;
grant select on public.research_queued_dispatch_reconciliations to service_role;
create trigger research_queued_dispatch_reconciliations_immutable before update or delete on public.research_queued_dispatch_reconciliations
 for each row execute function public.research_immutable();

-- Once a worker has acquired an admission, it cannot return to the pristine
-- queue state used as this proof. Terminal/identity restrictions remain intact.
create or replace function public.research_model_dispatch_immutable() returns trigger language plpgsql set search_path='' as $$ begin
 if tg_op='DELETE' or old.status not in ('queued','running') or (old.status='running' and new.status='queued') or
  (new.id,new.study_id,new.task_id,new.runtime,new.request_raw,new.request_sha256,new.created_at) is distinct from
  (old.id,old.study_id,old.task_id,old.runtime,old.request_raw,old.request_sha256,old.created_at) then raise exception 'Original model dispatch and terminal receipt are immutable';end if;
 return new;
end$$;

create function public.research_model_reconcile_queued(p_dispatch uuid,p_request_sha256 text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare d public.research_model_dispatches;t public.research_autonomy_turns;r public.research_queued_dispatch_reconciliations;
 original text;h text;proof jsonb;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 select * into strict d from public.research_model_dispatches where id=p_dispatch for update;
 if d.request_sha256 is distinct from p_request_sha256 then raise exception 'Exact original queued request hash required';end if;
 select * into r from public.research_queued_dispatch_reconciliations where dispatch_id=d.id;
 if found then
  if d.status<>'failed' or d.provenance->'queued_admission_reconciliation' is distinct from r.proof then raise exception 'Queued reconciliation differs from its original terminal receipt';end if;
  return jsonb_build_object('reconciled',true,'dispatch_id',d.id,'snapshot_sha256',r.snapshot_sha256);
 end if;
 select * into strict t from public.research_autonomy_turns where id=d.id for update;
 if d.status<>'queued' or d.runtime<>'openclaw-production-v1' or d.lease_token is not null or d.lease_until is not null
  or d.ended_at is not null or d.response_artifact_id is not null or d.response_sha256 is not null or d.provenance<>'{}'::jsonb
  or t.status not in ('failed','unknown','invalid-output') or t.ended_at is null or t.model_id<>'gpt-6.1-sol'
  or (t.study_id,t.task_id,t.request_sha256,t.request_raw) is distinct from (d.study_id,d.task_id,d.request_sha256,d.request_raw)
  or jsonb_typeof(t.request->'builder') is distinct from 'object'
  or exists(select 1 from public.research_builder_calls where dispatch_id=d.id)
  or exists(select 1 from public.research_artifacts where study_id=d.study_id and provenance->>'dispatch_id'=d.id::text)
  then return jsonb_build_object('reconciled',false,'reason','Original admission is not proven pristine and unclaimed.');end if;
 original=to_jsonb(d)::text;h=encode(sha256(convert_to(original,'UTF8')),'hex');
 proof=jsonb_build_object('version','queued-dispatch-reconciliation-v1','dispatch_id',d.id,'study_id',d.study_id,'task_id',d.task_id,
  'request_sha256',d.request_sha256,'snapshot_sha256',h,'original_status','queued','terminal_status','failed',
  'parent_turn_status',t.status,'parent_turn_request_sha256',t.request_sha256,'provider_calls',0,'provider_request_sent',false,
  'admission_state','pristine-unclaimed','claim_fence','original-dispatch-row-lock;terminal-parent-turn',
  'scope','Pre-transport admission closure only; no container cleanup claim, inference replay, refund, deadline reset or scientific validation.');
 insert into public.research_queued_dispatch_reconciliations(dispatch_id,study_id,task_id,request_sha256,snapshot_raw,snapshot_sha256,parent_turn_status,proof)
  values(d.id,d.study_id,d.task_id,d.request_sha256,original,h,t.status,proof);
 update public.research_model_dispatches set status='failed',ended_at=clock_timestamp(),
  provenance=jsonb_build_object('queued_admission_reconciliation',proof) where id=d.id;
 insert into public.research_autonomy_events(study_id,task_id,event,details) values(d.study_id,d.task_id,'queued-dispatch-reconciled',proof);
 return jsonb_build_object('reconciled',true,'dispatch_id',d.id,'snapshot_sha256',h);
end$$;

-- Keep the existing unknown/native recovery rules unchanged; add only pristine
-- queued admissions whose original parent turn can no longer be claimed.
create or replace function public.research_model_reconciliation_candidates(p_after uuid default null) returns setof jsonb
language sql stable security definer set search_path='' as $$
 select to_jsonb(d) from public.research_model_dispatches d
 join public.research_autonomy_tasks q on q.id=d.task_id and q.study_id=d.study_id
 join public.research_autonomy_turns t on t.id=d.id
 where (p_after is null or d.id>p_after) and jsonb_typeof(d.request_raw::jsonb->'builder')='object'
  and not exists(select 1 from public.research_model_reconciliations r where r.dispatch_id=d.id)
  and not exists(select 1 from public.research_queued_dispatch_reconciliations r where r.dispatch_id=d.id)
  and ((d.status in ('unknown','failed','invalid-output') and q.status<>'running'
    and not exists(select 1 from public.research_autonomy_turns turn where turn.task_id=q.id and turn.status='running')
    and not exists(select 1 from public.research_builder_calls c where c.task_id=q.id and c.status='running')
    and not exists(select 1 from public.research_model_dispatches live where live.task_id=q.id and live.status in ('queued','running')))
   or (d.status='queued' and d.runtime='openclaw-production-v1' and d.lease_token is null and d.lease_until is null
    and d.ended_at is null and d.response_artifact_id is null and d.response_sha256 is null and d.provenance='{}'::jsonb
    and t.status in ('failed','unknown','invalid-output') and t.ended_at is not null and t.model_id='gpt-6.1-sol'
    and (t.study_id,t.task_id,t.request_sha256,t.request_raw)=(d.study_id,d.task_id,d.request_sha256,d.request_raw)
    and jsonb_typeof(t.request->'builder')='object'
    and not exists(select 1 from public.research_builder_calls c where c.dispatch_id=d.id)
    and not exists(select 1 from public.research_artifacts a where a.study_id=d.study_id and a.provenance->>'dispatch_id'=d.id::text)))
 order by d.id limit 8
$$;
revoke all on function public.research_model_reconcile_queued(uuid,text),public.research_model_reconciliation_candidates(uuid) from public,anon,authenticated,service_role;
grant execute on function public.research_model_reconcile_queued(uuid,text),public.research_model_reconciliation_candidates(uuid) to service_role;
notify pgrst,'reload schema';
commit;
