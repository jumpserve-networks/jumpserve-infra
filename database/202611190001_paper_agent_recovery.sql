begin;
-- New admissions only. Preserve historical requests, providers, candidate drafts,
-- reservations, deadlines, terminal outcomes and all independent approval gates.
alter table public.research_paper_agent_sessions add column if not exists recovery_version integer check(recovery_version=1);
alter table public.research_paper_agent_sessions add column if not exists stop_code text check(stop_code in ('owner_cancel','action_limit','no_progress','deadline','policy_change'));

create or replace function public.research_paper_agent_recovery_guard() returns trigger language plpgsql set search_path='' as $$begin
 if old.recovery_version is not null and new.recovery_version is distinct from old.recovery_version or old.recovery_version is null and new.recovery_version is not null and (old.status<>'preparing' or old.request is not null)
  or old.stop_code='owner_cancel' and new.stop_code is distinct from old.stop_code or old.stop_code is not null and new.stop_code is distinct from old.stop_code and new.stop_code is distinct from 'owner_cancel' then raise exception 'Original repair recovery policy and owner stop are immutable';end if;
 return new;
end$$;
drop trigger if exists paper_agent_recovery_guard on public.research_paper_agent_sessions;
create trigger paper_agent_recovery_guard before update on public.research_paper_agent_sessions for each row execute function public.research_paper_agent_recovery_guard();

-- Reconstruct progress from immutable actions. Reads, duplicate delivery and
-- restarts do not reset the failure streak. Different failures and saved edits do.
create or replace function public.research_paper_agent_progress(repair uuid) returns jsonb language plpgsql stable set search_path='' as $$
declare a record;version integer;signature text;streak integer=0;output jsonb;begin
 select candidate_version into version from public.research_paper_agent_sessions where call_id=repair;
 for a in select candidate_version,result,status from public.research_paper_agent_actions where call_id=repair and name='apply_patch' and status='completed' order by position desc limit 3 loop
  if a.status<>'completed' or a.candidate_version<>version or a.result->'success' is distinct from 'true'::jsonb then exit;end if;
  begin output=(a.result->>'output')::jsonb;exception when others then exit;end;
  if output->'applied' is distinct from 'false'::jsonb or coalesce(output->>'failure_signature','') !~ '^[a-f0-9]{64}$' then exit;end if;
  if signature is null then signature=output->>'failure_signature';end if;
  if output->>'failure_signature' is distinct from signature then exit;end if;
  streak=streak+1;
 end loop;
 return jsonb_build_object('actions_used',(select count(*) from public.research_paper_agent_actions where call_id=repair),'repeated_failures',streak,'failure_signature',signature);
end$$;
create or replace function public.research_quality_result(workflow uuid) returns jsonb language sql stable set search_path='' as $$
 select public.research_quality_result_responses_v3(workflow)||jsonb_build_object('agent',(select to_jsonb(s)||public.research_paper_agent_progress(s.call_id) from public.research_paper_agent_sessions s join public.research_paper_quality_workflows w on w.current_call_id=s.call_id where w.id=workflow))
$$;
create or replace function public.research_paper_agent_capabilities() returns jsonb language sql stable set search_path='' as $$
 select '{"runtime":"managed-agents-v1","native_records":true,"finite_provider_limits":false,"recovery_version":1}'::jsonb
$$;

do $$declare body text;begin
 if to_regprocedure('public.research_paper_agent_control_native_v1(text,uuid,uuid,jsonb)') is null then
  select prosrc into strict body from pg_proc where oid='public.research_paper_agent_control(text,uuid,uuid,jsonb)'::regprocedure;
  execute 'create function public.research_paper_agent_control_native_v1(p_operation text,p_actor uuid,p_call uuid,p_payload jsonb default ''{}'') returns jsonb language plpgsql security definer set search_path='''' as '||quote_literal(body);
 end if;
 if to_regprocedure('public.research_paper_quality_control_native_v1(text,uuid,uuid,jsonb)') is null then
  select prosrc into strict body from pg_proc where oid='public.research_paper_quality_control(text,uuid,uuid,jsonb)'::regprocedure;
  execute 'create function public.research_paper_quality_control_native_v1(p_operation text,p_actor uuid,p_workflow uuid,p_payload jsonb default ''{}'') returns jsonb language plpgsql security definer set search_path='''' as '||quote_literal(body);
 end if;
end$$;
create or replace function public.research_paper_quality_control(p_operation text,p_actor uuid,p_workflow uuid,p_payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
declare result jsonb;begin
 result=public.research_paper_quality_control_native_v1(p_operation,p_actor,p_workflow,p_payload);
 if p_operation='admit' and result->'admitted'='true'::jsonb and result->'call'->>'provider_type'='managed_agent' and p_payload->'repair_recovery_version'='1'::jsonb then
  update public.research_paper_agent_sessions set recovery_version=1 where call_id=(result->'call'->>'id')::uuid and status='preparing' and request is null;
  result=public.research_quality_result(p_workflow)||'{"admitted":true}'::jsonb;
 end if;
 return result;
end$$;

create or replace function public.research_paper_agent_control(p_operation text,p_actor uuid,p_call uuid,p_payload jsonb default '{}') returns jsonb language plpgsql security definer set search_path='' as $$
#variable_conflict use_variable
declare s public.research_paper_agent_sessions;w public.research_paper_quality_workflows;c public.research_paper_quality_calls;progress jsonb;result jsonb;code text;checks jsonb;hash text;session jsonb;turn jsonb;eligible boolean;begin
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 select * into s from public.research_paper_agent_sessions where call_id=p_call for update;
 select * into w from public.research_paper_quality_workflows where id=s.workflow_id for update;
 select * into c from public.research_paper_quality_calls where id=s.call_id for update;
 if s.call_id is null or p_actor is null or p_actor<>s.owner_id or w.owner_id<>p_actor or public.research_assessment_deleted(w.study_id) or not exists(select 1 from public.research_study_owners where study_id=w.study_id and owner_id=p_actor)
  or not exists(select 1 from auth.users u join auth.identities i on i.user_id=u.id where u.id=p_actor and not coalesce(u.is_anonymous,true) and i.provider='google') then raise exception 'Verified active managed repair owner required';end if;
 if s.status in ('completed','failed','cancelled') then return public.research_paper_agent_control_native_v1(p_operation,p_actor,p_call,p_payload);end if;
 if w.current_call_id<>c.id or w.status not in ('running','uncertain') then raise exception 'The original current managed repair is required';end if;
 progress=public.research_paper_agent_progress(c.id);
 if p_operation='action_result' and s.recovery_version=1 and (progress->>'repeated_failures')::integer>=3
  and exists(select 1 from public.research_paper_agent_actions a where a.call_id=c.id and a.id=(p_payload->>'action_id')::uuid and a.status<>'completed') then raise exception 'Managed repair repeated failure limit reached; preserve checkpoint';end if;
 if p_operation in ('action_claim','action_ack') and s.recovery_version=1 and ((progress->>'actions_used')::integer>=22 or (progress->>'repeated_failures')::integer>=3) then
  if p_operation='action_ack' then return 'false'::jsonb;end if;
  -- A concurrent delivery of the already counted final action can finish its
  -- original lease or replay its immutable result. It cannot admit action 23.
  if exists(select 1 from public.research_paper_agent_actions a where a.call_id=c.id and a.turn_id=p_payload->'action'->>'turn_id' and a.provider_call_id=p_payload->'action'->>'call_id' and ((progress->>'repeated_failures')::integer<3 or a.status='completed')) then
   return public.research_paper_agent_control_native_v1(p_operation,p_actor,p_call,p_payload);
  end if;
  if (progress->>'repeated_failures')::integer>=3 then raise exception 'Managed repair repeated failure limit reached; preserve checkpoint';end if;
  raise exception 'Managed repair action limit reached; preserve checkpoint';
 end if;
 if p_operation='cancel_requested' then
  code=p_payload->>'stop_code';
  if code is null then code='owner_cancel';end if; -- Compatibility: legacy clients retain their original cancellation semantics.
  if code not in ('owner_cancel','action_limit','no_progress','deadline','policy_change') then raise exception 'A precise managed stop reason is required';end if;
  if code='action_limit' and (progress->>'actions_used')::integer<22 or code='no_progress' and (progress->>'repeated_failures')::integer<3 then raise exception 'Retained action evidence must establish the automatic stop';end if;
  result=public.research_paper_agent_control_native_v1(p_operation,p_actor,p_call,p_payload);
  update public.research_paper_agent_sessions set stop_code=case when stop_code='owner_cancel' then stop_code else code end where call_id=c.id;
  return public.research_quality_result(w.id);
 end if;
 if p_operation='failed' and s.stop_code='owner_cancel' then return public.research_paper_agent_control_native_v1('cancelled',p_actor,p_call,p_payload||jsonb_build_object('reason','The owner cancelled managed repair; provider stopping is confirmed.'));end if;
 if p_operation<>'checkpoint' then return public.research_paper_agent_control_native_v1(p_operation,p_actor,p_call,p_payload);end if;
 -- A checkpoint is not a successful provider turn or approval. Only confirmed
 -- stopping of the original session can yield its locally source-valid draft.
 checks=p_payload->'checks';session=p_payload->'session';turn=p_payload->'turn';
 hash=encode(sha256(convert_to(public.research_quality_canonical(w.source_json||jsonb_build_object('candidate',s.candidate)),'UTF8')),'hex');
 if s.recovery_version is distinct from 1 or coalesce(s.stop_code,'') not in ('action_limit','no_progress') or s.cancel_requested_at is null or s.provider_session_id is null or s.candidate_version<1 or s.candidate is not distinct from s.initial_candidate
  or session is distinct from s.session or turn is distinct from s.turn or session->>'id' is distinct from s.provider_session_id or session->>'status' is distinct from 'idle' or coalesce(turn->>'status','') not in ('cancelled','completed','failed') or turn->>'session_id' is distinct from s.provider_session_id or turn->'subagent_id' is distinct from 'null'::jsonb
  or checks->'passed' is distinct from 'true'::jsonb or checks->>'source_sha256' is distinct from hash or not public.research_valid_quality_candidate(w,s.candidate)
  or not exists(select 1 from public.research_paper_agent_events e where e.call_id=c.id and e.kind='controller_checks' and e.snapshot->'checks'->'passed'='true'::jsonb and e.snapshot->'checks'->>'source_sha256'=hash)
  or jsonb_typeof(p_payload->'items') is distinct from 'array' or jsonb_array_length(p_payload->'items')=0 or jsonb_array_length(p_payload->'items')<>(select count(*) from public.research_paper_agent_items where call_id=c.id)
  or exists(select 1 from jsonb_array_elements(p_payload->'items') m where m->>'retained_in' is distinct from 'research_paper_agent_items' or not exists(select 1 from public.research_paper_agent_items i where i.call_id=c.id and i.item_key=m->>'item_key' and i.content_sha256=m->>'sha256')) then raise exception 'A confirmed original stop, improved saved draft, full retained history and exact source-bound controller checks are required';end if;
 eligible=s.deadline_at>clock_timestamp() and w.deadline_at>clock_timestamp() and w.round<3 and public.research_paper_agent_limits_allow(w.study_id);
 if eligible then
  begin perform public.research_assert_quality_budget(w.study_id,case when w.step=4 then 200 else 100 end,1);
  exception when others then eligible=false;end;
 end if;
 update public.research_paper_agent_sessions set status=case when turn->>'status'='completed' then 'completed' when turn->>'status'='cancelled' then 'cancelled' else 'failed' end where call_id=c.id;
 update public.research_paper_quality_calls set status=case when eligible then 'completed' else 'failed' end,response=jsonb_build_object('runtime','managed-agents-v1','outcome','checkpoint','stop_code',s.stop_code,'session',session,'turn',turn,'items',p_payload->'items','checks',checks,'review_eligible',eligible) where id=c.id;
 update public.research_paper_quality_workflows set candidate=case when eligible then s.candidate else candidate end,checks=checks,round=case when eligible then round+1 else round end,status=case when eligible then 'review_pending' else 'needs_attention' end,phase=case when eligible then 'reviewing' else 'needs_attention' end,
  reason=case when eligible then 'Repair stopped at its bounded limit. The improved saved checkpoint is awaiting independent high-reasoning review.' else 'Repair stopped at its bounded limit. Its checkpoint is retained; original deadline, round or spending limits do not permit another review.' end where id=w.id;
 insert into public.research_paper_agent_events(call_id,workflow_id,study_id,kind,snapshot) values(c.id,w.id,w.study_id,'checkpoint',p_payload||jsonb_build_object('stop_code',s.stop_code,'review_eligible',eligible));
 return public.research_quality_result(w.id);
end$$;

do $$declare proc regprocedure;begin
 for proc in select oid::regprocedure from pg_proc where pronamespace='public'::regnamespace and proname in ('research_paper_agent_recovery_guard','research_paper_agent_progress','research_quality_result','research_paper_agent_capabilities','research_paper_quality_control_native_v1','research_paper_agent_control_native_v1','research_paper_quality_control','research_paper_agent_control') loop
  execute format('revoke all on function %s from public,anon,authenticated,service_role',proc);
 end loop;
end$$;
grant execute on function public.research_paper_quality_control(text,uuid,uuid,jsonb),public.research_paper_agent_control(text,uuid,uuid,jsonb),public.research_paper_agent_capabilities() to service_role;
notify pgrst,'reload schema';
commit;
