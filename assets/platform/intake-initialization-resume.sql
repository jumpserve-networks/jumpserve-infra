-- Database-owner release step. Execute only after exact installed source
-- readback, healthy heartbeat and the retained SSM command are verified.
begin;
set local lock_timeout='15s';
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
do $$ declare r public.research_intake_runtime;t public.research_autonomy_tasks;w public.research_autonomy_workflows;begin
 select * into strict r from public.research_intake_runtime where id for update;
 if r.enabled or r.status<>'ready' or r.seen_at is null or r.seen_at<=clock_timestamp()-interval '25 seconds'
 or r.configuration->>'source_binding' is distinct from '@BINDING@'
 or r.configuration->>'gateway_verified' is distinct from 'true'
 or r.configuration->>'native_version' is distinct from '2026.10.5'
 then raise exception 'Routing must be disabled and exact repaired intake source freshly ready';end if;
 if exists(select 1 from public.platform_settings where id and paused)
 or exists(select 1 from public.research_autonomy_tasks where stage='intake' and lease_token is not null)
 or exists(select 1 from public.research_model_dispatches where dispatch_lane='intake' and status in ('queued','running'))
 then raise exception 'Owner controls and original intake drain must permit resumption';end if;
 select * into strict t from public.research_autonomy_tasks where study_id='@STUDY@' and claim_id is null and intake_parent_id is null for update;
 select * into strict w from public.research_autonomy_workflows where study_id=t.study_id for update;
 if t.stage<>'intake' or t.status<>'blocked' or t.lease_token is not null or t.attempts<>0
 or t.reason<>'Autonomous operation unconfirmed (KeyError); reconcile retained identities before continuing.'
 or t.context<>'{"intake_pool_version":"warm-intake-v1"}'::jsonb
 or w.status not in ('running','completed-with-blockers') or w.deadline_at<=clock_timestamp()+interval '480 seconds'
 or (w.max_spend_cents is not null and w.committed_cents+5>w.max_spend_cents)
 or (w.max_attempts is not null and t.attempts>=w.max_attempts)
 or not public.autonomy_budget_allows('research_assessment',w.committed_cents,0,5,0)
 or exists(select 1 from public.research_autonomy_turns where study_id=t.study_id)
 or exists(select 1 from public.research_builder_calls where study_id=t.study_id)
 or exists(select 1 from public.research_model_dispatches where study_id=t.study_id)
 or exists(select 1 from public.research_autonomy_tasks where study_id=t.study_id and id<>t.id)
 or exists(select 1 from public.research_claims where study_id=t.study_id)
 or not exists(select 1 from public.research_paper_reviews where study_id=t.study_id and status='failed' and confirmed_at is null and confirmation is null and seeds='[]'::jsonb)
 then raise exception 'Only an untouched fresh-intake initialization failure may resume';end if;
 insert into public.research_autonomy_events(study_id,task_id,event,details)
 values(t.study_id,t.id,'intake-initialization-repaired',jsonb_build_object('release_id','@RELEASE@',
 'source_binding','@BINDING@','source_revision','@REVISION@','original_context',t.context,
 'original_reason',t.reason,'original_attempts',t.attempts,'original_committed_cents',w.committed_cents,
 'original_deadline_at',w.deadline_at,'uncertain_calls_replayed',false));
 update public.research_autonomy_tasks set status='queued',reason='Verified intake initializer installed; original source initialization queued.',next_at=clock_timestamp(),updated_at=clock_timestamp() where id=t.id;
 update public.research_autonomy_workflows set status='running',updated_at=clock_timestamp() where study_id=t.study_id;
 update public.research_paper_reviews set status='preparing',revision=revision+1,reason='Verified intake initializer installed; preparation resumed.',updated_at=clock_timestamp() where study_id=t.study_id;
 update public.research_intake_runtime set enabled=true where id;
 insert into public.platform_events(id,actor,kind,message,details)
 values('@RELEASE@','deployment-operator','intake-initialization-resumed','Verified intake initialization repair installed; original assessment resumed without replaying provider calls.',
 jsonb_build_object('study_id',t.study_id,'source_binding','@BINDING@','source_revision','@REVISION@','scientific_completion',false));
end $$;
select now() as resumed_at,to_jsonb(r) as runtime from public.research_intake_runtime r;
commit;
