begin;
create table public.research_autonomy_workflows (
 study_id uuid primary key references public.research_studies(id),
 initial_prompt text not null check(octet_length(initial_prompt)<=24000),
 initial_sha256 text not null check(initial_sha256=encode(sha256(convert_to(initial_prompt,'UTF8')),'hex')),
 max_spend_cents integer not null default 10000 check(max_spend_cents=10000),
 max_attempts integer not null default 25 check(max_attempts=25),
 committed_cents integer not null default 500 check(committed_cents between 0 and 10000),
 overhead_reservation_cents integer not null default 500 check(overhead_reservation_cents=500),
 status text not null default 'running' check(status in ('running','completed','completed-with-blockers','deadline','budget','cancelled')),
 reason text not null default 'Accepted; durable background preparation is pending.',
 created_at timestamptz not null default clock_timestamp(),
 deadline_at timestamptz not null default clock_timestamp()+interval '7 days',
 updated_at timestamptz not null default clock_timestamp(),
 check(deadline_at>created_at and deadline_at<=created_at+interval '7 days 1 second')
);
create table public.research_autonomy_tasks (
 id uuid primary key,study_id uuid not null references public.research_autonomy_workflows(study_id),
 claim_id uuid,stage text not null check(stage in ('intake','planning','comprehension','critic','execution','assessment')),
 status text not null default 'queued' check(status in ('queued','running','waiting','resolved','finished','blocked','attempt-limit','budget','deadline','cancelled')),
 label text check(label in ('untested','inconclusive','reproduced','discrepant')),
 attempts integer not null default 0 check(attempts between 0 and 25),
 context jsonb not null default '{}' check(jsonb_typeof(context)='object' and octet_length(context::text)<=256000),
 reason text not null default 'Waiting for a background worker.',required_inputs jsonb not null default '[]' check(jsonb_typeof(required_inputs)='array'),lease_token uuid,lease_until timestamptz,
 next_at timestamptz not null default clock_timestamp(),created_at timestamptz not null default clock_timestamp(),updated_at timestamptz not null default clock_timestamp(),
 unique(study_id,id),unique(study_id,claim_id),foreign key(study_id,claim_id) references public.research_claims(study_id,id),
 check((claim_id is null and label is null) or (claim_id is not null and label is not null)),
 check(status<>'resolved' or (claim_id is not null and label in ('reproduced','discrepant')))
);
create unique index research_autonomy_one_intake on public.research_autonomy_tasks(study_id) where claim_id is null;
create index research_autonomy_ready on public.research_autonomy_tasks(status,next_at);
create table public.research_autonomy_turns (
 id uuid primary key,study_id uuid not null,task_id uuid not null,number integer not null check(number between 1 and 25),
 stage text not null,prompt_version_id uuid not null references public.agent_prompt_versions(id),model_id text not null,
 request jsonb not null check(jsonb_typeof(request)='object' and octet_length(request::text)<=120000),
 request_raw text not null check(octet_length(request_raw)<=120000 and request=request_raw::jsonb),
 request_sha256 text not null check(request_sha256=encode(sha256(convert_to(request_raw,'UTF8')),'hex')),
 status text not null default 'running' check(status in ('running','complete','failed','invalid-output','unknown')),
 reserved_cents integer not null check(reserved_cents>0),estimated_cents integer check(estimated_cents>=0),
 raw_response text check(octet_length(raw_response)<=100000),response_sha256 text,
 output jsonb,usage jsonb not null default '{}',reason text,
 created_at timestamptz not null default clock_timestamp(),ended_at timestamptz,
 unique(task_id,number),foreign key(study_id,task_id) references public.research_autonomy_tasks(study_id,id),
 check(response_sha256 is not distinct from case when raw_response is null then null else encode(sha256(convert_to(raw_response,'UTF8')),'hex') end),
 check(status<>'complete' or (raw_response is not null and output is not null))
);
create table public.research_autonomy_job_commitments (
 job_id uuid primary key,study_id uuid not null,task_id uuid not null,
 definition_sha256 text not null check(definition_sha256 ~ '^[a-f0-9]{64}$'),
 reserved_cents integer not null check(reserved_cents>0),quote jsonb not null,
 created_at timestamptz not null default clock_timestamp(),
 foreign key(study_id,task_id) references public.research_autonomy_tasks(study_id,id)
);
create unique index research_autonomy_one_running_turn on public.research_autonomy_turns(task_id) where status='running';
create table public.research_autonomy_events (
 id uuid primary key default gen_random_uuid(),study_id uuid not null references public.research_autonomy_workflows(study_id),
 task_id uuid,event text not null,details jsonb not null,created_at timestamptz not null default clock_timestamp()
);
do $$ declare t text; begin
 foreach t in array array['workflows','tasks','turns','job_commitments','events'] loop
  execute format('alter table public.research_autonomy_%I enable row level security',t);
  execute format('revoke all on public.research_autonomy_%I from public,anon,authenticated',t);
  execute format('grant select,insert,update on public.research_autonomy_%I to service_role',t);
 end loop;
end $$;
create function public.research_autonomy_immutable() returns trigger language plpgsql set search_path='' as $$ begin
 if tg_op='DELETE' then raise exception 'Autonomous assessment history cannot be deleted'; end if;
 if tg_table_name='research_autonomy_workflows' then
  if (new.study_id,new.initial_prompt,new.initial_sha256,new.max_spend_cents,new.max_attempts,new.deadline_at,new.created_at,new.overhead_reservation_cents)
   is distinct from (old.study_id,old.initial_prompt,old.initial_sha256,old.max_spend_cents,old.max_attempts,old.deadline_at,old.created_at,old.overhead_reservation_cents) then raise exception 'Original authorization and limits are immutable'; end if;
 elsif tg_table_name='research_autonomy_tasks' then
  if (new.id,new.study_id,new.claim_id,new.created_at) is distinct from (old.id,old.study_id,old.claim_id,old.created_at) then raise exception 'Original task identity is immutable'; end if;
 elsif tg_table_name='research_autonomy_turns' then
  if old.status<>'running' or
   (new.id,new.study_id,new.task_id,new.number,new.stage,new.prompt_version_id,new.model_id,new.request,new.request_raw,new.request_sha256,new.reserved_cents,new.created_at)
   is distinct from (old.id,old.study_id,old.task_id,old.number,old.stage,old.prompt_version_id,old.model_id,old.request,old.request_raw,old.request_sha256,old.reserved_cents,old.created_at) then raise exception 'Original prompts and terminal attempts are immutable'; end if;
 end if;
 return new;
end $$;
create trigger research_autonomy_workflow_immutable before update or delete on public.research_autonomy_workflows for each row execute function public.research_autonomy_immutable();
create trigger research_autonomy_task_immutable before update or delete on public.research_autonomy_tasks for each row execute function public.research_autonomy_immutable();
create trigger research_autonomy_turn_immutable before update or delete on public.research_autonomy_turns for each row execute function public.research_autonomy_immutable();
create trigger research_autonomy_commitment_immutable before update or delete on public.research_autonomy_job_commitments for each row execute function public.research_immutable();
create trigger research_autonomy_event_immutable before update or delete on public.research_autonomy_events for each row execute function public.research_immutable();

create function public.research_autonomy_control(p_operation text,p_actor uuid,p_study uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w public.research_autonomy_workflows;t public.research_autonomy_tasks;r public.research_autonomy_turns;
 j public.research_autonomy_job_commitments;v jsonb; result jsonb; cents integer; original text; begin
 -- One short global gate serializes admission, not model calls or experiments.
 perform pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));
 if p_operation='start' then
  if p_actor is null or p_study is null or p_payload->'paper'->>'study_kind' is distinct from 'paper' then raise exception 'Authenticated paper intake required'; end if;
  original=p_payload->>'initial_prompt';
  select * into w from public.research_autonomy_workflows where study_id=p_study;
  if found then
   if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper workspace required'; end if;
   if w.initial_prompt is distinct from original then raise exception 'Request ID already identifies another initial prompt'; end if;
   return (select to_jsonb(s)||jsonb_build_object('autonomy',to_jsonb(w)) from public.research_studies s where id=p_study);
  end if;
  result=public.research_create_study(p_actor,p_study,p_payload->'paper');
  insert into public.research_autonomy_workflows(study_id,initial_prompt,initial_sha256) values(p_study,original,encode(sha256(convert_to(original,'UTF8')),'hex')) returning * into w;
  insert into public.research_autonomy_tasks(id,study_id,claim_id,stage,label) values((p_payload->>'intake_id')::uuid,p_study,null,'intake',null);
  insert into public.research_autonomy_events(study_id,event,details) values(p_study,'initial-prompt',jsonb_build_object('sha256',w.initial_sha256,'maximum_spend_usd',100,'elapsed_days',7,'attempts_per_claim',25,'overhead_reserved_cents',500,'controller_slot_reservation_cents',5));
  return result||jsonb_build_object('autonomy',to_jsonb(w));
 end if;
 if p_operation='lease' then
  -- Never silently repeat an uncertain provider invocation or external launch.
  update public.research_autonomy_turns set status='unknown',reason='Worker lease expired; provider completion and charge remain unconfirmed.',ended_at=clock_timestamp()
   where status='running' and task_id in (select id from public.research_autonomy_tasks where status='running' and lease_until<clock_timestamp());
  update public.research_autonomy_tasks set status='blocked',reason='Worker lease expired; reconcile retained provider/experiment identity before more work.',lease_token=null,lease_until=null,updated_at=clock_timestamp()
   where status='running' and lease_until<clock_timestamp();
  update public.research_autonomy_workflows stopped set status='completed-with-blockers',reason='All tasks stopped; unconfirmed provider or experiment outcomes require reconciliation.',updated_at=clock_timestamp()
   where stopped.status='running' and exists(select 1 from public.research_autonomy_tasks a where a.study_id=stopped.study_id)
   and not exists(select 1 from public.research_autonomy_tasks a where a.study_id=stopped.study_id and a.status in ('queued','waiting','running'));
  update public.research_autonomy_workflows set status='deadline',reason='Seven-day elapsed limit reached; no new work admitted.',updated_at=clock_timestamp()
   where status='running' and deadline_at<=clock_timestamp();
  update public.research_autonomy_workflows set status='budget',reason='Remaining budget cannot cover another bounded controller slot.',updated_at=clock_timestamp()
   where status='running' and committed_cents+5>max_spend_cents;
  update public.research_autonomy_tasks a set status='deadline',reason='Paper elapsed-time limit reached.',updated_at=clock_timestamp()
   from public.research_autonomy_workflows b where a.study_id=b.study_id and b.status='deadline' and a.status in ('queued','waiting');
  update public.research_autonomy_tasks a set status='budget',reason='Paper budget cannot admit another controller slot.',updated_at=clock_timestamp()
   from public.research_autonomy_workflows b where a.study_id=b.study_id and b.status='budget' and a.status in ('queued','waiting');
  update public.research_queue_jobs q set status='cancelled',reason='Autonomous budget, cancellation or elapsed limit prevents this queued launch.',updated_at=clock_timestamp()
   from public.research_autonomy_job_commitments c join public.research_autonomy_workflows b on b.study_id=c.study_id
   where q.id=c.job_id and q.status='queued' and (b.deadline_at<=clock_timestamp()+make_interval(secs=>coalesce((c.quote->>'required_seconds')::integer,180)) or b.status in ('cancelled','deadline','budget'));
  if (select count(*) from public.research_autonomy_tasks where status='running')>=4 then return null; end if;
  select a.* into t from public.research_autonomy_tasks a join public.research_autonomy_workflows b on a.study_id=b.study_id
   where a.status in ('queued','waiting') and a.next_at<=clock_timestamp() and b.status='running' and b.deadline_at>clock_timestamp()+interval '180 seconds'
   and (select count(*) from public.research_autonomy_tasks x where x.study_id=a.study_id and x.status='running')<2
   order by a.next_at,a.created_at,a.id for update of a skip locked limit 1;
  if not found then return null; end if;
  update public.research_autonomy_tasks set status='running',lease_token=gen_random_uuid(),lease_until=clock_timestamp()+interval '300 seconds',updated_at=clock_timestamp() where id=t.id returning * into t;
  update public.research_autonomy_workflows set committed_cents=committed_cents+5,updated_at=clock_timestamp() where study_id=t.study_id;
  insert into public.research_autonomy_events(study_id,task_id,event,details) values(t.study_id,t.id,'controller-slot',jsonb_build_object('reserved_cents',5,'basis','Conservative bounded orchestration reservation, not a measured charge'));
  select * into strict w from public.research_autonomy_workflows where study_id=t.study_id;
  return to_jsonb(t)||jsonb_build_object('workflow',to_jsonb(w),'actor_id',(select owner_id from public.research_study_owners where study_id=t.study_id));
 end if;
 if p_actor is null or p_study is null then raise exception 'Owner identity required'; end if;
 if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Private paper workspace required'; end if;
 select * into strict w from public.research_autonomy_workflows where study_id=p_study for update;
 if p_operation='cancel' then
  update public.research_autonomy_workflows set status='cancelled',reason='Owner cancelled further autonomous work.',updated_at=clock_timestamp() where study_id=p_study returning * into w;
  update public.research_autonomy_tasks set status='cancelled',reason='Owner cancelled further work.',updated_at=clock_timestamp() where study_id=p_study and status in ('queued','waiting');
  return to_jsonb(w);
 end if;
 if p_operation='seed' then
  if w.status<>'running' or w.deadline_at<=clock_timestamp() then raise exception 'Paper no longer accepts new claims'; end if;
  if jsonb_array_length(p_payload->'claims')>200 then raise exception 'Claim inventory exceeds campaign bounds'; end if;
  for v in select value from jsonb_array_elements(p_payload->'claims') loop
   if not exists(select 1 from public.research_claims where study_id=p_study and id=(v->>'claim_id')::uuid) then raise exception 'Recorded source-bound claim required'; end if;
   insert into public.research_autonomy_tasks(id,study_id,claim_id,stage,label,context)
    values((v->>'id')::uuid,p_study,(v->>'claim_id')::uuid,'planning','untested',coalesce(v->'context','{}')) on conflict(study_id,claim_id) do nothing;
  end loop;
  if (select count(*) from public.research_autonomy_tasks where study_id=p_study and claim_id is not null)>200 then raise exception 'Inventory exceeds 200 claims; retained source coverage requires a separate campaign'; end if;
  return jsonb_build_object('seeded',true);
 end if;
 select * into strict t from public.research_autonomy_tasks where id=(p_payload->>'task_id')::uuid and study_id=p_study for update;
 if t.status<>'running' or t.lease_token is distinct from (p_payload->>'token')::uuid or t.lease_until<=clock_timestamp() then raise exception 'Current fenced worker lease required'; end if;
 if p_operation='begin' then
  select * into r from public.research_autonomy_turns where id=(p_payload->>'id')::uuid;
  if found then
   if r.task_id<>t.id or r.request is distinct from p_payload->'request' then raise exception 'Turn ID reused for another prompt'; end if;
   return to_jsonb(r)||jsonb_build_object('replayed',true);
  end if;
  if w.status<>'running' then return jsonb_build_object('denied',case when w.status in ('budget','cancelled') then w.status else 'deadline' end); end if;
  if w.deadline_at<=clock_timestamp()+interval '90 seconds' then return jsonb_build_object('denied','deadline'); end if;
  if t.attempts>=w.max_attempts then return jsonb_build_object('denied','attempt-limit'); end if;
  if exists(select 1 from public.research_autonomy_turns where task_id=t.id and status='running') then return jsonb_build_object('denied','in-flight'); end if;
  cents=(p_payload->>'reserved_cents')::integer;
  if cents is null or cents<1 or cents>10000 then raise exception 'A positive conservative cost reservation is required'; end if;
  if w.committed_cents+cents>w.max_spend_cents then return jsonb_build_object('denied','budget'); end if;
  if not exists(select 1 from public.agent_prompt_versions v join public.agent_prompt_settings s on s.active_version_id=v.id and s.module_id=v.module_id where v.id=(p_payload->>'prompt_version_id')::uuid and v.module_id='research-autonomy' and v.published_at is not null) then raise exception 'Published evaluated autonomous prompt required'; end if;
  update public.research_autonomy_workflows set committed_cents=committed_cents+cents,updated_at=clock_timestamp() where study_id=p_study;
  update public.research_autonomy_tasks set attempts=attempts+1 where id=t.id returning * into t;
  insert into public.research_autonomy_turns(id,study_id,task_id,number,stage,prompt_version_id,model_id,request,request_raw,request_sha256,reserved_cents)
   values((p_payload->>'id')::uuid,p_study,t.id,t.attempts,t.stage,(p_payload->>'prompt_version_id')::uuid,p_payload->>'model_id',p_payload->'request',p_payload->>'request_raw',p_payload->>'request_sha256',cents) returning * into r;
  return to_jsonb(r)||jsonb_build_object('replayed',false);
 elsif p_operation='finish' then
  select * into strict r from public.research_autonomy_turns where id=(p_payload->>'id')::uuid and task_id=t.id for update;
  if r.status<>'running' then
   if r.raw_response is distinct from p_payload->>'raw_response' or r.status is distinct from p_payload->>'status' then raise exception 'Preserve terminal response'; end if;
   return to_jsonb(r);
  end if;
  original=p_payload->>'raw_response';
  update public.research_autonomy_turns set status=p_payload->>'status',raw_response=original,
   response_sha256=case when original is null then null else encode(sha256(convert_to(original,'UTF8')),'hex') end,
   output=p_payload->'output',usage=coalesce(p_payload->'usage','{}'),estimated_cents=(p_payload->>'estimated_cents')::integer,
   reason=p_payload->>'reason',ended_at=clock_timestamp() where id=r.id returning * into r;
  if r.estimated_cents>r.reserved_cents then
   update public.research_autonomy_workflows set status='budget',reason='Usage exceeded the reserved price ceiling; reconcile costs before further work.',updated_at=clock_timestamp() where study_id=p_study;
  end if;
  return to_jsonb(r);
 elsif p_operation='reserve-job' then
  select * into j from public.research_autonomy_job_commitments where job_id=(p_payload->>'job_id')::uuid;
  if found then
   if j.study_id<>p_study or j.definition_sha256 is distinct from p_payload->>'definition_sha256' then raise exception 'Job ID has another immutable commitment'; end if;
   return to_jsonb(j);
  end if;
  cents=(p_payload->>'reserved_cents')::integer;
  if (p_payload->>'required_seconds')::integer is null or (p_payload->>'required_seconds')::integer not between 1 and 3780 then raise exception 'A bounded experiment duration is required'; end if;
  if w.status<>'running' or w.deadline_at<=clock_timestamp()+make_interval(secs=>(p_payload->>'required_seconds')::integer) or cents is null or cents<1 or w.committed_cents+cents>w.max_spend_cents then return jsonb_build_object('denied','budget-or-deadline'); end if;
  update public.research_autonomy_workflows set committed_cents=committed_cents+cents,updated_at=clock_timestamp() where study_id=p_study;
  insert into public.research_autonomy_job_commitments values((p_payload->>'job_id')::uuid,p_study,t.id,p_payload->>'definition_sha256',cents,p_payload->'quote',default) returning * into j;
  return to_jsonb(j);
 elsif p_operation='advance' then
  if p_payload->>'status' in ('blocked','budget','deadline','cancelled') then
   update public.research_autonomy_turns set status='unknown',reason='Task stopped before response persistence was confirmed; original prompt and cost reservation retained.',ended_at=clock_timestamp() where task_id=t.id and status='running';
  end if;
  if p_payload->>'status'='resolved' and not exists(select 1 from public.research_assessments a where a.study_id=p_study and a.id=(p_payload->'context'->>'assessment_id')::uuid and a.claim_id=t.claim_id and a.label=p_payload->>'label' and a.campaign_id is not null) then raise exception 'Resolution requires a retained claim assessment and campaign'; end if;
  update public.research_autonomy_tasks set status=p_payload->>'status',stage=p_payload->>'stage',context=p_payload->'context',
   required_inputs=coalesce((select jsonb_agg(b->>'required_input') from jsonb_array_elements(coalesce(p_payload->'context'->'blockers','[]')) b),'[]'),
   label=case when claim_id is null then null else coalesce(p_payload->>'label',label) end,reason=p_payload->>'reason',
   lease_token=null,lease_until=null,next_at=clock_timestamp()+make_interval(secs=>least(300,greatest(0,coalesce((p_payload->>'delay_seconds')::integer,0)))),updated_at=clock_timestamp() where id=t.id returning * into t;
  insert into public.research_autonomy_events(study_id,task_id,event,details) values(p_study,t.id,'task-transition',jsonb_build_object('stage',t.stage,'status',t.status,'label',t.label,'reason',t.reason,'attempts',t.attempts,'usage',p_payload->'usage'));
  if not exists(select 1 from public.research_autonomy_tasks where study_id=p_study and status in ('queued','waiting','running')) then
   update public.research_autonomy_workflows set status=case when exists(select 1 from public.research_autonomy_tasks where study_id=p_study and claim_id is not null) and not exists(select 1 from public.research_autonomy_tasks where study_id=p_study and status not in ('resolved','finished')) then 'completed' else 'completed-with-blockers' end,
    reason='All admitted tasks reached a recorded outcome; unresolved findings and coverage limits remain visible.',updated_at=clock_timestamp() where study_id=p_study and status='running';
  end if;
  return to_jsonb(t);
 end if;
 raise exception 'Unsupported autonomous operation';
end $$;

create function public.research_autonomy_queue_guard() returns trigger language plpgsql set search_path='' as $$
declare c public.research_autonomy_job_commitments;w public.research_autonomy_workflows; begin
 select * into c from public.research_autonomy_job_commitments where job_id=new.id;
 if not found then return new; end if;
 select * into strict w from public.research_autonomy_workflows where study_id=c.study_id;
 if new.study_id<>c.study_id or new.definition_sha256<>c.definition_sha256 then raise exception 'Queue definition differs from its reserved experiment'; end if;
 if new.status in ('queued','running') and (w.status<>'running' or w.deadline_at<=clock_timestamp()+make_interval(secs=>coalesce((c.quote->>'required_seconds')::integer,180))) then raise exception 'Autonomous authorization cannot cover this execution duration'; end if;
 return new;
end $$;
create trigger research_autonomy_queue_admission before insert or update on public.research_queue_jobs for each row execute function public.research_autonomy_queue_guard();
revoke all on function public.research_autonomy_control(text,uuid,uuid,jsonb),public.research_autonomy_immutable(),public.research_autonomy_queue_guard() from public,anon,authenticated;
grant execute on function public.research_autonomy_control(text,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
