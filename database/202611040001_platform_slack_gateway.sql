begin;

-- Slack membership is checked by the trusted Socket Mode adapter. This record
-- delegates task admission only; it never manufactures a Google JWT or changes
-- the owner-only pause/release/cancellation interfaces.
create table public.platform_slack_bindings (
 team_id text primary key check(team_id ~ '^T[A-Z0-9]+$'),
 channel_id text not null check(channel_id ~ '^C[A-Z0-9]+$'),
 dm_owner text not null check(dm_owner ~ '^U[A-Z0-9]+$'),
 delegated_by uuid not null references public.platform_operators(user_id),
 enabled boolean not null default false,
 created_at timestamptz not null default clock_timestamp()
);
create table public.platform_slack_requests (
 id uuid primary key,
 team_id text not null references public.platform_slack_bindings(team_id),
 channel_id text not null, sender_id text not null,
 session_id uuid not null, payload jsonb not null,
 task_id uuid not null references public.platform_tasks(id),
 created_at timestamptz not null default clock_timestamp()
);
create table public.platform_slack_records (
 id uuid primary key, call_id uuid not null,
 kind text not null check(kind in ('model-request','model-response','model-outcome')),
 sha256 text not null check(sha256 ~ '^[a-f0-9]{64}$'),
 byte_count integer not null check(byte_count between 0 and 5000000),
 storage_path text not null unique,
 created_at timestamptz not null default clock_timestamp(),
 check(storage_path='slack/'||id::text||'/'||sha256)
);
do $$declare t text;begin
 foreach t in array array['platform_slack_bindings','platform_slack_requests','platform_slack_records'] loop
  execute format('alter table public.%I enable row level security',t);
  execute format('revoke all on public.%I from public,anon,authenticated,service_role',t);
  execute format('grant select on public.%I to service_role',t);
 end loop;
 foreach t in array array['platform_slack_requests','platform_slack_records'] loop
  execute format('create trigger %I before update or delete on public.%I for each row execute function public.platform_immutable()',t||'_immutable',t);
 end loop;
end$$;

create function public.platform_slack_authority(p_team text,p_channel text,p_sender text)
returns public.platform_slack_bindings language plpgsql stable security definer set search_path='' as $$
declare binding public.platform_slack_bindings;begin
 select b.* into binding from public.platform_slack_bindings b
 join public.platform_operators o on o.user_id=b.delegated_by and o.role='owner'
 where b.team_id=p_team and b.enabled;
 if binding.team_id is null or p_channel is null or p_sender is null or p_sender !~ '^U[A-Z0-9]+$'
  or not (p_channel=binding.channel_id or p_channel ~ '^D[A-Z0-9]+$' and p_sender=binding.dm_owner)
 then raise exception 'Slack conversation is not authorized' using errcode='42501';end if;
 return binding;
end$$;

create function public.platform_slack_status(p_team text,p_channel text,p_sender text)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare binding public.platform_slack_bindings;result jsonb;begin
 binding=public.platform_slack_authority(p_team,p_channel,p_sender);
 -- Aggregate health is shared; private owner task titles/objectives and model
 -- transcripts are never included in a group status response.
 select jsonb_build_object('version','platform-slack-status-v1','observed_at',clock_timestamp(),
  'paused',s.paused,'automatic_releases',s.automatic_releases,
  'authorization_version',s.authorization_version,'worker_seen_at',s.worker_seen_at,
  'worker_status',s.worker_status,
  'task_counts',(select coalesce(jsonb_object_agg(status,n),'{}'::jsonb) from
   (select status,count(*) n from public.platform_tasks group by status)c),
  'shared_tasks',coalesce((select jsonb_agg(x) from (
   select distinct t.id,t.title,t.status,t.cancel_requested,t.created_at,t.updated_at
   from public.platform_slack_requests r join public.platform_tasks t on t.id=r.task_id
   where r.team_id=p_team and (p_channel=binding.channel_id and r.channel_id=binding.channel_id
    or p_channel ~ '^D' and r.channel_id=p_channel and r.sender_id=p_sender)
   order by t.created_at desc limit 12)x),'[]'::jsonb)) into result
 from public.platform_settings s where s.id;
 return result;
end$$;

create function public.platform_slack_request(p_request uuid,p_team text,p_channel text,p_sender text,p_session uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare binding public.platform_slack_bindings;previous public.platform_slack_requests;
 settings public.platform_settings;task_id uuid;repos text[];begin
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 binding=public.platform_slack_authority(p_team,p_channel,p_sender);
 if p_request is null or p_session is null or jsonb_typeof(p_payload) is distinct from 'object'
  or (p_payload-array['title','objective','repositories'])<>'{}'::jsonb
  or jsonb_typeof(p_payload->'title') is distinct from 'string'
  or jsonb_typeof(p_payload->'objective') is distinct from 'string'
  or length(p_payload->>'title') not between 1 and 160
  or length(p_payload->>'objective') not between 1 and 12000
  or jsonb_typeof(p_payload->'repositories') is distinct from 'array'
 then raise exception 'Invalid Slack task request';end if;
 select array_agg(x) into repos from jsonb_array_elements_text(p_payload->'repositories')x;
 if coalesce(cardinality(repos),0) not between 1 and 3
  or (select count(distinct x) from unnest(repos)x)<>cardinality(repos)
  or not repos<@array['jumpserve-networks/jumpserve-front-end','jumpserve-networks/jumpserve-back-end','jumpserve-networks/jumpserve-infra']
 then raise exception 'Slack repository scope differs';end if;
 select * into previous from public.platform_slack_requests where id=p_request;
 if found then
  if (previous.team_id,previous.channel_id,previous.sender_id,previous.session_id,previous.payload)
   is distinct from (p_team,p_channel,p_sender,p_session,p_payload) then raise exception 'Slack request identity differs';end if;
  return jsonb_build_object('task_id',previous.task_id,'recorded',true,'replayed',true);
 end if;
 select * into strict settings from public.platform_settings where id for share;
 if settings.authorization_version is null then raise exception 'Standing authorization is not configured';end if;
 select t.id into task_id from public.platform_slack_requests r join public.platform_tasks t on t.id=r.task_id
 where r.team_id=p_team and r.channel_id=p_channel and r.sender_id=p_sender and r.payload=p_payload
  and (r.session_id=p_session or t.status in ('queued','investigating','implementing','testing','publishing','merging','deploying','verifying','reconciling')
   and not t.cancel_requested and t.deadline_at>clock_timestamp())
 order by r.created_at desc limit 1;
 if task_id is null then
  task_id=gen_random_uuid();
  insert into public.platform_tasks(id,requested_by,title,objective,repositories,authorization_version,max_reserved_cents,deadline_at)
  values(task_id,binding.delegated_by,p_payload->>'title',p_payload->>'objective',repos,
   settings.authorization_version,-1,clock_timestamp()+interval '6 hours');
 end if;
 -- The existing category-budget trigger selects the current database policy.
 insert into public.platform_slack_requests(id,team_id,channel_id,sender_id,session_id,payload,task_id)
 values(p_request,p_team,p_channel,p_sender,p_session,p_payload,task_id);
 insert into public.platform_events(id,task_id,actor,kind,message,details)
 values(p_request,task_id,'slack','slack-requested','Platform improvement requested from an authorized Slack conversation.',
  jsonb_build_object('version','platform-slack-request-v1','team_id',p_team,'channel_id',p_channel,
   'sender_id',p_sender,'session_id',p_session,'delegated_by',binding.delegated_by));
 return jsonb_build_object('task_id',task_id,'recorded',true,
  'status',(select t.status from public.platform_tasks t where t.id=task_id),'paused',settings.paused);
end$$;

create function public.platform_slack_record(p_id uuid,p_call uuid,p_kind text,p_sha text,p_bytes integer,p_path text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare previous public.platform_slack_records;begin
 if p_id is null or p_call is null or p_kind is null or p_sha is null or p_bytes is null or p_path is null
 then raise exception 'Incomplete Slack evidence record';end if;
 insert into public.platform_slack_records(id,call_id,kind,sha256,byte_count,storage_path)
 values(p_id,p_call,p_kind,p_sha,p_bytes,p_path) on conflict(id) do nothing;
 select * into strict previous from public.platform_slack_records where id=p_id;
 if (previous.call_id,previous.kind,previous.sha256,previous.byte_count,previous.storage_path)
  is distinct from (p_call,p_kind,p_sha,p_bytes,p_path) then raise exception 'Original Slack evidence identity differs';end if;
 return jsonb_build_object('id',previous.id,'sha256',previous.sha256,'recorded',true);
end$$;

revoke all on function public.platform_slack_authority(text,text,text),public.platform_slack_status(text,text,text),
 public.platform_slack_request(uuid,text,text,text,uuid,jsonb),public.platform_slack_record(uuid,uuid,text,text,integer,text)
 from public,anon,authenticated,service_role;
grant execute on function public.platform_slack_status(text,text,text),
 public.platform_slack_request(uuid,text,text,text,uuid,jsonb),public.platform_slack_record(uuid,uuid,text,text,integer,text) to service_role;

commit;
