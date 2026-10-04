-- Dedicated public read-only computational study; application deployment is separate.
begin;
create table public.leo_study_campaigns (
  id text primary key,
  title text not null,
  status text not null check(status in ('running','complete','incomplete')),
  protocol jsonb not null,
  protocol_sha256 text not null check(length(protocol_sha256)=64),
  artifact_commit text not null,
  paper_sha256 text not null,
  planned_samples integer not null check(planned_samples>0),
  recorded_samples integer not null check(recorded_samples>=0),
  limitations jsonb not null,
  provenance jsonb not null,
  created_at timestamptz not null default now()
);
create table public.leo_study_configurations (
  id text primary key,
  campaign_id text not null references public.leo_study_campaigns(id),
  country text not null,
  constellation text not null,
  satellites integer not null check(satellites>0),
  requested_terminals integer not null check(requested_terminals>0),
  deployed_terminals integer not null check(deployed_terminals between 0 and requested_terminals),
  placement text not null,
  beam_policy text not null,
  ku_gbps numeric not null check(ku_gbps>0 and ku_gbps<100),
  variant text not null check(variant in ('paper','artifact')),
  cells integer not null check(cells>0),
  lost_capacity_gbps numeric not null check(lost_capacity_gbps>0),
  published_capacity_gbps numeric not null check(published_capacity_gbps>0),
  unique(campaign_id,id)
);
create index leo_study_configurations_campaign on public.leo_study_configurations(campaign_id,country);
create table public.leo_study_samples (
  id text primary key,
  campaign_id text not null,
  configuration_id text not null,
  second integer not null check(second>=0),
  capacity_gbps numeric not null check(capacity_gbps>=0 and capacity_gbps<1000000),
  rf_demand_gbps numeric not null check(rf_demand_gbps>=capacity_gbps and rf_demand_gbps<1000000),
  cell_bound_gbps numeric not null check(cell_bound_gbps>=capacity_gbps and cell_bound_gbps<1000000),
  failover_percent numeric not null check(failover_percent>=0 and failover_percent<1000000),
  served_cells integer not null check(served_cells>=0),
  allocated_beams integer not null check(allocated_beams>=0),
  validation_errors jsonb not null,
  graph_sha256 text not null,
  demands_sha256 text not null,
  terminal_sha256 text not null,
  runner_sha256 text not null,
  wall_seconds numeric not null check(wall_seconds>=0),
  foreign key(campaign_id,configuration_id) references public.leo_study_configurations(campaign_id,id),
  unique(configuration_id,second)
);
create index leo_study_samples_campaign on public.leo_study_samples(campaign_id,configuration_id,second);
create table public.leo_study_summaries (
  campaign_id text not null references public.leo_study_campaigns(id),
  country text not null,
  published_gbps numeric not null,
  mean_gbps numeric not null,
  min_gbps numeric not null,
  max_gbps numeric not null,
  relative_difference_percent numeric not null,
  failover_percent numeric not null,
  snapshots integer not null check(snapshots>0),
  assessment text not null,
  primary key(campaign_id,country)
);
create table public.leo_study_papers (
  campaign_id text not null references public.leo_study_campaigns(id),
  reference_number integer not null check(reference_number between 0 and 96),
  citation text not null,
  kind text not null,
  source_url text,
  download_status text not null,
  reading_status text not null,
  pages integer,
  sha256 text,
  version_note text,
  reading_notes text,
  retrieval_audit jsonb not null,
  primary key(campaign_id,reference_number)
);
create table public.leo_study_claims (
  campaign_id text not null references public.leo_study_campaigns(id),
  claim_id text not null,
  figure text not null,
  description text not null,
  coverage text not null,
  limitation text not null,
  primary key(campaign_id,claim_id)
);
do $security$
declare relation text;
begin
  foreach relation in array array['leo_study_campaigns','leo_study_configurations','leo_study_samples','leo_study_summaries','leo_study_papers','leo_study_claims'] loop
    execute format('alter table public.%I enable row level security',relation);
    execute format('revoke all on public.%I from anon,authenticated',relation);
    execute format('grant select on public.%I to anon,authenticated',relation);
    execute format('grant all on public.%I to service_role',relation);
    execute format('create policy leo_study_public_read on public.%I for select to anon,authenticated using(true)',relation);
    -- The existing event trigger installs a restrictive rule that denies anon.
    execute format('drop policy if exists jumpserve_require_signed_in_user on public.%I',relation);
    execute format('create policy jumpserve_require_signed_in_user on public.%I as restrictive for all to authenticated using ((select auth.uid()) is not null and (select auth.jwt()->>''is_anonymous'') is distinct from ''true'') with check ((select auth.uid()) is not null and (select auth.jwt()->>''is_anonymous'') is distinct from ''true'')',relation);
  end loop;
end $security$;
alter table public.agent_prompt_versions drop constraint agent_prompt_versions_module_id_check;
alter table public.agent_prompt_versions add constraint agent_prompt_versions_module_id_check check(module_id in ('congestion-control-emulated','congestion-control-real-world','leo-emergency-failover'));
alter table public.agent_prompt_settings drop constraint agent_prompt_settings_module_id_check;
alter table public.agent_prompt_settings add constraint agent_prompt_settings_module_id_check check(module_id in ('congestion-control-emulated','congestion-control-real-world','leo-emergency-failover'));
alter table public.agent_sessions drop constraint agent_sessions_module_id_check;
alter table public.agent_sessions add constraint agent_sessions_module_id_check check(module_id in ('congestion-control-emulated','congestion-control-real-world','leo-emergency-failover'));
insert into public.agent_prompt_settings(module_id) values('leo-emergency-failover') on conflict(module_id) do nothing;
notify pgrst,'reload schema';
commit;
