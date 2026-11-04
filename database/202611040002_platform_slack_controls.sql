begin;

-- Expand the existing owner delegation to direct operator controls. No Google
-- JWT is created and no participant is enrolled as a Google platform owner.
create function public.platform_slack_task(p_team text,p_channel text,p_sender text,p_task uuid default null)
returns jsonb language plpgsql stable security definer set search_path='' as $$
declare binding public.platform_slack_bindings;result jsonb;begin
 binding=public.platform_slack_authority(p_team,p_channel,p_sender);
 result=jsonb_build_object('version','platform-slack-operations-v2',
  'requires_additional_owner_approval',false,
  'tools',jsonb_build_array('jumpserve_status','jumpserve_request','jumpserve_task','jumpserve_control'),
  'controls',jsonb_build_array('pause','resume','disable-releases','enable-releases','cancel'));
 if p_task is null then return result;end if;
 if not exists(select 1 from public.platform_slack_requests r where r.task_id=p_task and r.team_id=p_team
  and (p_channel=binding.channel_id and r.channel_id=binding.channel_id
   or p_channel ~ '^D' and r.channel_id=p_channel and r.sender_id=p_sender))
 then raise exception 'Task is not shared in this conversation' using errcode='42501';end if;
 return result||jsonb_build_object(
  'task',(select to_jsonb(t) from (select id,title,objective,repositories,status,reason,priority,
   max_reserved_cents,committed_cents,deadline_at,cancel_requested,created_at,updated_at
   from public.platform_tasks where id=p_task)t),
  -- Raw logs, artifacts, original model messages and release payloads remain
  -- private; structured task progress does not expose unrelated conversations.
  'events',coalesce((select jsonb_agg(e) from (select sequence::text,id,kind,created_at
   from public.platform_events where task_id=p_task order by public.platform_events.sequence desc limit 40)e),'[]'::jsonb),
  'changes',coalesce((select jsonb_agg(c) from (select id,repository,base_sha,head_sha,merge_sha,
   pr_number,pr_url,status,created_at,updated_at from public.platform_changes
   where task_id=p_task order by created_at desc,id desc limit 20)c),'[]'::jsonb),
  'releases',coalesce((select jsonb_agg(r) from (select id,component,repository,revision,status,
   created_at,updated_at from public.platform_releases where task_id=p_task
   order by created_at desc,id desc limit 20)r),'[]'::jsonb),
  'runs',coalesce((select jsonb_agg(r) from (select id,number,status,created_at,ended_at,
   exists(select 1 from public.platform_run_reconciliations x where x.run_id=platform_runs.id) as reconciled
   from public.platform_runs where task_id=p_task order by number desc limit 30)r),'[]'::jsonb));
end$$;

create function public.platform_slack_control(p_request uuid,p_team text,p_channel text,p_sender text,
 p_session uuid,p_action text,p_task uuid default null)
returns jsonb language plpgsql security definer set search_path='' as $$
declare binding public.platform_slack_bindings;previous public.platform_requests;
 settings public.platform_settings;task public.platform_tasks;payload jsonb;result jsonb;begin
 if p_request is null or p_session is null or p_action is null
  or p_action not in ('pause','resume','disable-releases','enable-releases','cancel')
  or (p_action='cancel') is distinct from (p_task is not null)
 then raise exception 'Invalid Slack operator control';end if;
 perform pg_advisory_xact_lock(hashtextextended('platform-supervisor-v1',0));
 binding=public.platform_slack_authority(p_team,p_channel,p_sender);
 payload=jsonb_build_object('version','platform-slack-control-v2','team_id',p_team,
  'channel_id',p_channel,'sender_id',p_sender,'session_id',p_session,'task_id',p_task);
 select * into previous from public.platform_requests where id=p_request;
 if found then
  if (previous.actor_id,previous.action,previous.payload) is distinct from
   (binding.delegated_by,'slack-'||p_action,payload)
  then raise exception 'Control request ID already identifies another action';end if;
  return previous.result||jsonb_build_object('replayed',true);
 end if;
 select * into strict settings from public.platform_settings where id for update;
 if p_action='cancel' then
  perform public.platform_slack_task(p_team,p_channel,p_sender,p_task);
  select * into strict task from public.platform_tasks where id=p_task for update;
  if task.status in ('completed','rolled-back','cancelled','deadline','budget')
  then raise exception 'Task already has a terminal outcome';end if;
  update public.platform_tasks set cancel_requested=true,
   status=case when status='queued' then 'cancelled' else status end,
   reason='Slack operator requested cancellation; in-flight external actions must reconcile before stopping.',
   updated_at=clock_timestamp() where id=p_task returning * into task;
  result=jsonb_build_object('action',p_action,'task_id',p_task,'cancel_requested',true,
   'status',task.status,'recorded',true);
 else
  if p_action in ('resume','enable-releases') and settings.authorization_version is null
  then raise exception 'Standing authorization is not configured';end if;
  update public.platform_settings set
   paused=case when p_action='pause' then true when p_action='resume' then false else paused end,
   automatic_releases=case when p_action='disable-releases' then false when p_action='enable-releases' then true else automatic_releases end,
   revision=revision+1,updated_at=clock_timestamp() where id returning * into settings;
  result=jsonb_build_object('action',p_action,'recorded',true,'paused',settings.paused,
   'automatic_releases',settings.automatic_releases,'revision',settings.revision);
 end if;
 insert into public.platform_events(id,task_id,actor,kind,message,details)
 values(p_request,p_task,'slack-operator','slack-'||p_action,
  case p_action when 'pause' then 'New supervisor work paused from Slack; in-flight operations retain their identities.'
   when 'resume' then 'Supervisor admission resumed from Slack under standing authority.'
   when 'disable-releases' then 'Automatic merges and releases disabled from Slack.'
   when 'enable-releases' then 'Automatic merges and releases enabled from Slack under standing authority.'
   else 'Cancellation requested from Slack; uncertain operations must reconcile before stopping.' end,
  payload||jsonb_build_object('delegated_by',binding.delegated_by,'result',result));
 insert into public.platform_requests(id,actor_id,action,payload,result)
 values(p_request,binding.delegated_by,'slack-'||p_action,payload,result);
 return result;
end$$;

revoke all on function public.platform_slack_task(text,text,text,uuid) from public,anon,authenticated;
revoke all on function public.platform_slack_control(uuid,text,text,text,uuid,text,uuid) from public,anon,authenticated;
grant execute on function public.platform_slack_task(text,text,text,uuid) to service_role;
grant execute on function public.platform_slack_control(uuid,text,text,text,uuid,text,uuid) to service_role;

commit;
