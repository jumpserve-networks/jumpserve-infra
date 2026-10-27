begin;
-- Service-only coordination. Scientific protocols and per-claim criteria stay
-- append-only in their original relations. No existing assessment is resumed.
alter table public.research_network_executions drop constraint research_network_executions_runner_check;
alter table public.research_network_executions add constraint research_network_executions_runner_check
 check(runner in ('emulated-netem-v1','real-world-iperf-v1','custom-package-v1','bounded-tcp-v1','netem-iperf-v1','source-arithmetic-v1'));
do $migration$ declare definition text; old text; begin
 definition=pg_get_functiondef('public.research_queue_enqueue(uuid,uuid,uuid,jsonb,text)'::regprocedure);
 old=$old$('emulated-netem-v1','real-world-iperf-v1','custom-package-v1','bounded-tcp-v1')$old$;
 if strpos(definition,old)=0 then raise exception 'Unexpected queue runner allowlist'; end if;
 execute replace(definition,old,$new$('emulated-netem-v1','real-world-iperf-v1','custom-package-v1','bounded-tcp-v1','netem-iperf-v1','source-arithmetic-v1')$new$);
end $migration$;

create table public.research_shared_campaigns(
 id uuid primary key references public.research_campaigns(id),
 study_id uuid not null references public.research_studies(id),
 campaign_id uuid not null, acquisition_sha256 text not null check(acquisition_sha256 ~ '^[a-f0-9]{64}$'),
 acquisition jsonb not null check(jsonb_typeof(acquisition)='object'),created_at timestamptz not null default clock_timestamp(),
 unique(study_id,acquisition_sha256),foreign key(study_id,campaign_id) references public.research_campaigns(study_id,id)
);
create table public.research_shared_campaign_members(
 id uuid primary key default gen_random_uuid(),task_id uuid not null references public.research_autonomy_tasks(id),study_id uuid not null,
 claim_id uuid not null,campaign_id uuid not null,protocol_id uuid not null,created_at timestamptz not null default clock_timestamp(),
 unique(task_id,protocol_id),foreign key(study_id,claim_id) references public.research_claims(study_id,id),
 foreign key(study_id,campaign_id) references public.research_campaigns(study_id,id),
 foreign key(study_id,protocol_id) references public.research_protocols(study_id,id)
);
alter table public.research_shared_campaigns enable row level security;
alter table public.research_shared_campaign_members enable row level security;
revoke all on public.research_shared_campaigns,public.research_shared_campaign_members from public,anon,authenticated;
grant select,insert on public.research_shared_campaigns,public.research_shared_campaign_members to service_role;
create trigger research_shared_campaigns_immutable before update or delete on public.research_shared_campaigns for each row execute function public.research_immutable();
create trigger research_shared_members_immutable before update or delete on public.research_shared_campaign_members for each row execute function public.research_immutable();

create function public.research_shared_campaign_bind(p_study uuid,p_actor uuid,p_task uuid,p_claim uuid,p_sha text,p_acquisition jsonb,p_campaign uuid,p_protocol uuid,p_records jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare prior public.research_shared_campaigns; member public.research_shared_campaign_members; r jsonb; check_record jsonb; begin
 perform pg_advisory_xact_lock(hashtextextended(p_study::text,0));
 if not exists(select 1 from public.research_study_owners where study_id=p_study and owner_id=p_actor) then raise exception 'Study not found'; end if;
 if not exists(select 1 from public.research_autonomy_tasks where id=p_task and study_id=p_study and claim_id=p_claim) then raise exception 'Claim task identity differs'; end if;
 if p_sha !~ '^[a-f0-9]{64}$' or jsonb_typeof(p_acquisition) is distinct from 'object' or jsonb_typeof(p_records) is distinct from 'array' then raise exception 'Acquisition identity required'; end if;
 select * into prior from public.research_shared_campaigns where study_id=p_study and acquisition_sha256=p_sha;
 if found and prior.acquisition is distinct from p_acquisition then raise exception 'Acquisition hash collision or changed identity'; end if;
 select * into member from public.research_shared_campaign_members where task_id=p_task and protocol_id=p_protocol;
 if found then
  if member.study_id<>p_study or member.claim_id<>p_claim or member.protocol_id<>p_protocol or member.campaign_id is distinct from prior.campaign_id then raise exception 'Task already bound to another acquisition'; end if;
  return jsonb_build_object('campaign_id',prior.campaign_id,'shared',true);
 end if;
 if prior.id is null then
  perform public.research_append_bundle(p_study,p_actor,p_records);
  insert into public.research_shared_campaigns(id,study_id,campaign_id,acquisition_sha256,acquisition) values(p_campaign,p_study,p_campaign,p_sha,p_acquisition) returning * into prior;
 else
  -- Preserve this claim's complete protocol, including its own hypothesis and
  -- comparison rule, while referencing the first acquisition's original jobs.
  for r in select value from jsonb_array_elements(p_records) where value->>'kind'='protocols' loop
   perform public.research_append(p_study,p_actor,'protocols',r->'record');
  end loop;
  for r in select value from jsonb_array_elements(p_records) where value->>'kind'='claim_checks' loop
   check_record=jsonb_set(r->'record','{campaign_id}',to_jsonb(prior.campaign_id));
   perform public.research_append(p_study,p_actor,'claim_checks',check_record);
  end loop;
 end if;
 insert into public.research_shared_campaign_members(task_id,study_id,claim_id,campaign_id,protocol_id) values(p_task,p_study,p_claim,prior.campaign_id,p_protocol);
 return jsonb_build_object('campaign_id',prior.campaign_id,'shared',prior.campaign_id<>p_campaign);
end $$;
revoke all on function public.research_shared_campaign_bind(uuid,uuid,uuid,uuid,text,jsonb,uuid,uuid,jsonb) from public,anon,authenticated;
grant execute on function public.research_shared_campaign_bind(uuid,uuid,uuid,uuid,text,jsonb,uuid,uuid,jsonb) to service_role;
notify pgrst,'reload schema';
commit;
