begin;
select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));

-- User authorization: "All active and future assessments", 2026-10-31.
-- This immutable record governs aggregate funding only. No scientific criteria,
-- deadline, reservation, per-invocation resource bound or uncertain call changes.
create table public.research_assessment_budget_policies (
 id text primary key,
 max_spend_cents integer check(max_spend_cents is null or max_spend_cents>=10000),
 authorization_text text not null,
 authorized_by text not null,
 scope text not null,
 created_at timestamptz not null default clock_timestamp()
);
alter table public.research_assessment_budget_policies enable row level security;
revoke all on public.research_assessment_budget_policies from public,anon,authenticated,service_role;
grant select on public.research_assessment_budget_policies to service_role;
create trigger research_assessment_budget_policy_immutable before update or delete on public.research_assessment_budget_policies
 for each row execute function public.research_immutable();
insert into public.research_assessment_budget_policies(id,max_spend_cents,authorization_text,authorized_by,scope)
 values('unlimited-assessment-defaults-20261031',null,'All active and future assessments',
 'Lab operator via Codex conversation, 2026-10-31',
 'All unexpired active assessments and future assessments; original deadlines, commitments, cancellation, per-experiment limits and uncertain-call safeguards remain enforced.');

alter table public.research_autonomy_workflows alter column max_spend_cents set default null;
comment on column public.research_autonomy_workflows.max_spend_cents is
 'Aggregate reservation ceiling in cents. Explicit NULL means unlimited. New assessments inherit the immutable unlimited-assessment-defaults-20261031 operator policy. Original limits and subsequent amendments remain recorded.';
create or replace function public.research_autonomy_initial_budget() returns trigger
 language plpgsql set search_path='' as $$ begin
 if new.max_spend_cents is not null or not exists(select 1 from public.research_assessment_budget_policies
   where id='unlimited-assessment-defaults-20261031' and max_spend_cents is null) then
  raise exception 'New assessments must inherit the recorded unlimited aggregate-budget policy';
 end if;
 return new;
end $$;

create function public.research_assessment_inherit_budget_policy() returns trigger
 language plpgsql set search_path='' as $$ declare policy public.research_assessment_budget_policies; begin
 select * into strict policy from public.research_assessment_budget_policies where id='unlimited-assessment-defaults-20261031';
 insert into public.research_autonomy_events(study_id,event,details)
 values(new.study_id,'budget-policy-inherited',jsonb_build_object('version','assessment-budget-policy-v1',
   'policy_id',policy.id,'max_spend_cents',new.max_spend_cents,'authorization',policy.authorization_text,
   'authorized_by',policy.authorized_by,'initial_sha256',new.initial_sha256,'committed_cents',new.committed_cents,
   'deadline_at',new.deadline_at,'scope',policy.scope));
 return new;
end $$;
revoke all on function public.research_assessment_inherit_budget_policy() from public,anon,authenticated;
create trigger research_assessment_inherit_budget_policy after insert on public.research_autonomy_workflows
 for each row execute function public.research_assessment_inherit_budget_policy();

-- Change only the initial-prompt event's funding metadata in the latest intake
-- implementation. Preserve all intervening wrappers and authorization checks.
do $migration$ declare item record; definition text; changes integer:=0; begin
 for item in select p.oid from pg_proc p join pg_namespace n on n.oid=p.pronamespace
   where n.nspname='public' and p.proname like 'research_autonomy%'
 loop
  definition=pg_get_functiondef(item.oid);
  if strpos(definition,$old$'maximum_spend_usd',100,$old$)>0 then
   execute replace(definition,$old$'maximum_spend_usd',100,$old$,$new$'maximum_spend_usd',null,$new$);
   changes=changes+1;
  end if;
 end loop;
 if changes<>1 then raise exception 'Expected exactly one current intake funding-metadata definition, found %',changes;end if;
end $migration$;

-- Catch assessments admitted during the rollout under the same serialized gate.
-- The deployed RPC preserves original counters, checkpoints and deadlines and
-- resumes only safely budget-stopped tasks, never uncertain or blocked calls.
do $amend$ declare item record; begin
 for item in select study_id from public.research_autonomy_workflows
   where status in ('running','budget','completed-with-blockers') and max_spend_cents is not null
     and deadline_at>clock_timestamp()+interval '480 seconds'
   order by study_id
 loop
  perform public.research_autonomy_set_budget(item.study_id,
    md5('unlimited-assessment-defaults-20261031:'||item.study_id::text)::uuid,
    null,true,'Lab operator via Codex conversation, 2026-10-31','All active and future assessments');
 end loop;
end $amend$;
notify pgrst,'reload schema';
commit;
