begin;

create table public.platform_operator_enrollments (
 email text primary key check(email=lower(email) and position('@' in email)>1),role text not null check(role in ('owner','viewer')),
 created_at timestamptz not null default clock_timestamp()
);
create table public.platform_operators (
 user_id uuid primary key references auth.users(id), role text not null check(role in ('owner','viewer','revoked')),
 created_at timestamptz not null default clock_timestamp()
);
create table public.platform_authorizations (
 version text primary key, policy_sha256 text not null check(policy_sha256 ~ '^[a-f0-9]{64}$'),
 document jsonb not null, authorized_by uuid references public.platform_operators(user_id),
 source_instruction text not null, created_at timestamptz not null default clock_timestamp()
);
create table public.platform_settings (
 id boolean primary key default true check(id), authorization_version text references public.platform_authorizations(version),
 paused boolean not null default true, automatic_releases boolean not null default true,
 worker_id uuid, worker_seen_at timestamptz, worker_status text not null default 'not-configured', worker_reason text,
 revision bigint not null default 0, updated_at timestamptz not null default clock_timestamp()
);
insert into public.platform_settings(id) values(true);
create table public.platform_tasks (
 id uuid primary key, requested_by uuid not null references public.platform_operators(user_id),
 title text not null check(length(title) between 1 and 160), objective text not null check(length(objective) between 1 and 12000),
 repositories text[] not null check(cardinality(repositories) between 1 and 3),
 authorization_version text not null references public.platform_authorizations(version),
 status text not null default 'queued' check(status in ('queued','investigating','implementing','testing','publishing','merging','deploying','verifying','reconciling','completed','rolled-back','blocked','cancelled','deadline','budget')),
 reason text not null default 'Queued for the platform supervisor.', priority integer not null default 100 check(priority between 0 and 1000),
 max_reserved_cents integer not null check(max_reserved_cents between 100 and 1000000), committed_cents integer not null default 0 check(committed_cents>=0 and committed_cents<=max_reserved_cents),
 deadline_at timestamptz not null, cancel_requested boolean not null default false,
 lease_token uuid, lease_until timestamptz, worker_id uuid, checkpoint jsonb not null default '{}',
 created_at timestamptz not null default clock_timestamp(), updated_at timestamptz not null default clock_timestamp()
);
create index platform_tasks_queue on public.platform_tasks(priority,created_at,id) where status='queued';
create table public.platform_events (
 sequence bigint generated always as identity primary key, id uuid not null unique,
 task_id uuid references public.platform_tasks(id), actor text not null, kind text not null,
 message text not null check(length(message) between 1 and 4000), details jsonb not null default '{}',
 created_at timestamptz not null default clock_timestamp(),check(octet_length(details::text)<=32000)
);
create index platform_events_task on public.platform_events(task_id,sequence desc);
create table public.platform_requests (
 id uuid primary key, actor_id uuid not null, action text not null, payload jsonb not null, result jsonb not null,
 created_at timestamptz not null default clock_timestamp()
);
create table public.platform_artifacts (
 id uuid primary key, task_id uuid not null references public.platform_tasks(id), name text not null,
 sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'), byte_count integer not null check(byte_count between 0 and 5000000),
 storage_path text not null unique, media_type text not null, provenance jsonb not null,
 created_at timestamptz not null default clock_timestamp()
);
create table public.platform_runs (
 id uuid primary key, task_id uuid not null references public.platform_tasks(id),
 number integer not null, request_sha256 text not null, request_artifact_id uuid not null references public.platform_artifacts(id),
 response_artifact_id uuid references public.platform_artifacts(id), status text not null default 'running' check(status in ('running','complete','failed','unknown')),
 reserved_cents integer not null, usage jsonb, reason text, created_at timestamptz not null default clock_timestamp(), ended_at timestamptz,
 unique(task_id,number)
);
create table public.platform_changes (
 id uuid primary key,task_id uuid not null references public.platform_tasks(id), repository text not null,
 base_sha text not null, head_sha text, tree_sha256 text not null, summary text not null,
 patch_artifact_id uuid not null references public.platform_artifacts(id), checks_artifact_id uuid not null references public.platform_artifacts(id),
 pr_number integer,pr_url text,merge_sha text,status text not null default 'tested',details jsonb not null default '{}',
 created_at timestamptz not null default clock_timestamp(),updated_at timestamptz not null default clock_timestamp()
);
create index platform_changes_versions on public.platform_changes(task_id,repository,created_at desc);
create table public.platform_run_reconciliations (
 run_id uuid primary key references public.platform_runs(id),task_id uuid not null references public.platform_tasks(id),
 artifact_id uuid not null references public.platform_artifacts(id),proof jsonb not null,created_at timestamptz not null default clock_timestamp()
);
create table public.platform_operations (
 id uuid primary key,task_id uuid not null references public.platform_tasks(id), kind text not null check(kind in ('publish','merge','deploy','verify','rollback')),
 request_sha256 text not null, request jsonb not null, status text not null default 'pending' check(status in ('pending','confirmed','failed','unknown')),
 result jsonb,created_at timestamptz not null default clock_timestamp(),updated_at timestamptz not null default clock_timestamp()
);
create table public.platform_releases (
 id uuid primary key,task_id uuid not null references public.platform_tasks(id), component text not null,
 repository text not null, revision text not null,status text not null default 'pending',external_id text,
 verification jsonb,details jsonb not null default '{}',created_at timestamptz not null default clock_timestamp(),updated_at timestamptz not null default clock_timestamp(),
 unique(task_id,component,revision)
);

create function public.platform_is_operator(p_write boolean default false) returns boolean language sql stable security definer set search_path='' as $$
 select exists(select 1 from public.platform_operators o where o.user_id=auth.uid() and o.role in ('owner','viewer') and (not p_write or o.role='owner'))
 and coalesce(auth.jwt()->'app_metadata'->>'provider'='google' or coalesce(auth.jwt()->'app_metadata'->'providers','[]'::jsonb) ? 'google',false)
$$;
revoke all on function public.platform_is_operator(boolean) from public,anon;
grant execute on function public.platform_is_operator(boolean) to authenticated;

create function public.platform_enroll_operator() returns void language plpgsql security definer set search_path='' as $$
declare enrollment public.platform_operator_enrollments;begin
 if auth.uid() is null or not coalesce(auth.jwt()->'app_metadata'->>'provider'='google' or coalesce(auth.jwt()->'app_metadata'->'providers','[]'::jsonb) ? 'google',false) then return;end if;
 select e.* into enrollment from public.platform_operator_enrollments e join auth.users u on lower(u.email)=e.email where u.id=auth.uid() and u.email_confirmed_at is not null;
 if found then insert into public.platform_operators(user_id,role) values(auth.uid(),enrollment.role) on conflict(user_id) do nothing;end if;
end$$;
revoke all on function public.platform_enroll_operator() from public,anon,service_role;
grant execute on function public.platform_enroll_operator() to authenticated;

create function public.platform_immutable() returns trigger language plpgsql set search_path='' as $$begin
 raise exception 'Original platform records are immutable; append a new event or version';
end$$;
do $$declare t text;begin
 foreach t in array array['platform_operator_enrollments','platform_operators','platform_authorizations','platform_settings','platform_tasks','platform_events','platform_requests','platform_artifacts','platform_runs','platform_run_reconciliations','platform_changes','platform_operations','platform_releases'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role',t);
  execute format('grant select on public.%I to service_role',t);
 end loop;
 foreach t in array array['platform_authorizations','platform_events','platform_requests','platform_artifacts','platform_run_reconciliations'] loop
  execute format('create trigger %I before update or delete on public.%I for each row execute function public.platform_immutable()',t||'_immutable',t);
 end loop;
end$$;
grant select on public.platform_events to authenticated;
create policy platform_operator_events on public.platform_events for select to authenticated using((select public.platform_is_operator(false)));

create function public.platform_control(p_action text,p_request uuid,p_task uuid default null,p_payload jsonb default '{}') returns jsonb
language plpgsql security definer set search_path='' as $$
declare previous public.platform_requests;settings public.platform_settings;task public.platform_tasks;result jsonb;repos text[];begin
 perform public.platform_enroll_operator();
 if not public.platform_is_operator(true) then raise exception 'Platform owner access required' using errcode='42501';end if;
 if p_request is null or jsonb_typeof(p_payload) is distinct from 'object' then raise exception 'Invalid platform control';end if;
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 select * into previous from public.platform_requests where id=p_request;
 if found then
  if (previous.actor_id,previous.action,previous.payload) is distinct from (auth.uid(),p_action,p_payload||jsonb_build_object('task_id',p_task)) then raise exception 'Control request ID already identifies another action';end if;
  return previous.result||jsonb_build_object('replayed',true);
 end if;
 select * into strict settings from public.platform_settings where id for update;
 if p_action='enqueue' then
  if settings.authorization_version is null then raise exception 'Supervisor authorization is not configured';end if;
  if p_task is null or jsonb_typeof(p_payload->'repositories')<>'array' or length(coalesce(p_payload->>'title','')) not between 1 and 160 or length(coalesce(p_payload->>'objective','')) not between 1 and 12000
   or (p_payload-array['title','objective','repositories','max_reserved_cents','elapsed_seconds'])<>'{}'::jsonb then raise exception 'Invalid platform task';end if;
  select array_agg(x) into repos from jsonb_array_elements_text(p_payload->'repositories') x;
  if cardinality(repos) not between 1 and 3 or (select count(distinct x) from unnest(repos)x)<>cardinality(repos)
   or not repos<@array['jumpserve-networks/jumpserve-front-end','jumpserve-networks/jumpserve-back-end','jumpserve-networks/jumpserve-infra'] then raise exception 'Repository scope differs from standing authorization';end if;
  if coalesce((p_payload->>'max_reserved_cents')::integer,10000) not between 100 and 1000000 or coalesce((p_payload->>'elapsed_seconds')::integer,21600) not between 300 and 604800 then raise exception 'Invalid task limits';end if;
  insert into public.platform_tasks(id,requested_by,title,objective,repositories,authorization_version,max_reserved_cents,deadline_at)
   values(p_task,auth.uid(),p_payload->>'title',p_payload->>'objective',repos,settings.authorization_version,coalesce((p_payload->>'max_reserved_cents')::integer,10000),clock_timestamp()+make_interval(secs=>coalesce((p_payload->>'elapsed_seconds')::integer,21600))) returning * into task;
  result=jsonb_build_object('task_id',task.id,'status',task.status);
 elsif p_action in ('pause','resume','disable-releases','enable-releases') then
  if p_payload<>'{}'::jsonb or p_task is not null then raise exception 'Unexpected control fields';end if;
  if p_action='resume' and settings.authorization_version is null then raise exception 'Standing authorization required';end if;
  update public.platform_settings set paused=case when p_action='pause' then true when p_action='resume' then false else paused end,
   automatic_releases=case when p_action='disable-releases' then false when p_action='enable-releases' then true else automatic_releases end,revision=revision+1,updated_at=clock_timestamp() where id;
  result=jsonb_build_object('action',p_action,'recorded',true);
 elsif p_action='cancel' then
  if p_payload<>'{}'::jsonb then raise exception 'Unexpected cancellation fields';end if;
  select * into strict task from public.platform_tasks where id=p_task for update;
  if task.status in ('completed','rolled-back','cancelled','deadline','budget') then raise exception 'Task already has a terminal outcome';end if;
  update public.platform_tasks set cancel_requested=true,status=case when status='queued' then 'cancelled' else status end,
   reason='Owner requested cancellation; in-flight external actions must reconcile before stopping.',updated_at=clock_timestamp() where id=task.id;
  result=jsonb_build_object('task_id',task.id,'cancel_requested',true);
 else raise exception 'Unsupported platform control';end if;
 insert into public.platform_events(id,task_id,actor,kind,message,details) values(p_request,p_task,'operator',p_action,
  case p_action when 'enqueue' then 'Platform improvement queued.' when 'pause' then 'New work paused; in-flight operations retain their identities.' when 'resume' then 'Platform supervisor admission resumed.' when 'disable-releases' then 'Automatic merges and production releases disabled.' when 'enable-releases' then 'Automatic merges and production releases enabled under standing authorization.' else 'Cancellation requested.' end,result);
 insert into public.platform_requests values(p_request,auth.uid(),p_action,p_payload||jsonb_build_object('task_id',p_task),result,clock_timestamp());
 return result;
end$$;
revoke all on function public.platform_control(text,uuid,uuid,jsonb) from public,anon,service_role;
grant execute on function public.platform_control(text,uuid,uuid,jsonb) to authenticated;

create function public.platform_snapshot(p_task uuid default null,p_before_event bigint default null,p_before_task uuid default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb;items jsonb;events jsonb;begin
 perform public.platform_enroll_operator();
 if not public.platform_is_operator(false) then raise exception 'Platform operator access required' using errcode='42501';end if;
 select coalesce(jsonb_agg(x),'[]') into items from (select id,title,objective,repositories,status,reason,priority,max_reserved_cents,committed_cents,deadline_at,cancel_requested,authorization_version,created_at,updated_at
  from public.platform_tasks where (p_task is null or id=p_task) and (p_before_task is null or (created_at,id)<(select created_at,id from public.platform_tasks where id=p_before_task)) order by created_at desc,id desc limit 50)x;
 select coalesce(jsonb_agg(x),'[]') into events from (select sequence::text,id,task_id,actor,kind,message,details,created_at from public.platform_events
  where (p_task is null or task_id=p_task) and (p_before_event is null or sequence<p_before_event) order by public.platform_events.sequence desc limit 100)x;
 result=jsonb_build_object('version','platform-supervisor-v1','operator_id',auth.uid(),'operator_role',(select role from public.platform_operators where user_id=auth.uid()),
  'settings',(select to_jsonb(s)-'id'-'worker_id' from public.platform_settings s where id),'authorization',(select jsonb_build_object('version',a.version,'policy_sha256',a.policy_sha256,'created_at',a.created_at) from public.platform_authorizations a join public.platform_settings s on s.authorization_version=a.version where s.id),
  'tasks',items,'events',events,'has_more_tasks',jsonb_array_length(items)=50,'has_more_events',jsonb_array_length(events)=100,
  'changes',coalesce((select jsonb_agg(x) from (select id,task_id,repository,base_sha,head_sha,tree_sha256,summary,pr_number,pr_url,merge_sha,status,details,created_at,updated_at from public.platform_changes where p_task is not null and task_id=p_task order by created_at desc limit 20)x),'[]'),
  'releases',coalesce((select jsonb_agg(x) from (select * from public.platform_releases where p_task is not null and task_id=p_task order by created_at desc limit 20)x),'[]'),
  'runs',coalesce((select jsonb_agg(x) from (select r.id,r.task_id,r.number,r.status,r.reserved_cents,r.usage,r.reason,r.request_sha256,r.request_artifact_id,r.response_artifact_id,r.created_at,r.ended_at,
   exists(select 1 from public.platform_run_reconciliations c where c.run_id=r.id) as reconciled from public.platform_runs r where p_task is not null and r.task_id=p_task order by r.number desc limit 30)x),'[]'),
  'artifacts',coalesce((select jsonb_agg(x) from (select id,task_id,name,sha256,byte_count,media_type,provenance,created_at from public.platform_artifacts where p_task is not null and task_id=p_task order by created_at desc limit 50)x),'[]'));
 return result;
end$$;
revoke all on function public.platform_snapshot(uuid,bigint,uuid) from public,anon,service_role;
grant execute on function public.platform_snapshot(uuid,bigint,uuid) to authenticated;

-- Private artifact access uses a checked projection, never a caller path.
create function public.platform_artifact_location(p_id uuid) returns jsonb language plpgsql stable security definer set search_path='' as $$
declare a public.platform_artifacts;begin
 if not public.platform_is_operator(false) then raise exception 'Platform operator access required' using errcode='42501';end if;
 select * into strict a from public.platform_artifacts where id=p_id;
 return jsonb_build_object('path',a.storage_path,'name',a.name,'sha256',a.sha256,'byte_count',a.byte_count,'media_type',a.media_type);
end$$;
revoke all on function public.platform_artifact_location(uuid) from public,anon,service_role;
grant execute on function public.platform_artifact_location(uuid) to authenticated;

insert into storage.buckets(id,name,public,file_size_limit) values('platform-supervisor-private','platform-supervisor-private',false,5000000) on conflict(id) do nothing;
create policy platform_operator_artifacts on storage.objects for select to authenticated using(bucket_id='platform-supervisor-private' and (select public.platform_is_operator(false)));
do $$begin
 if exists(select 1 from pg_publication where pubname='supabase_realtime') then alter publication supabase_realtime add table public.platform_events;end if;
end$$;
notify pgrst,'reload schema';
commit;
