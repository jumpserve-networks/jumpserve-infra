-- Dedicated measurement relations. No authentication secrets or requester PII.
begin;

create table public.delay_study_campaigns (
  id text primary key,
  title text not null,
  paper_doi text not null,
  status text not null check (status in ('planned','running','completed','partial','failed')),
  protocol text not null,
  protocol_sha256 text not null,
  manifest_sha256 text not null,
  kernel_commit text not null,
  planned_trials integer not null check (planned_trials > 0),
  bootstrap_replicates integer not null default 2000,
  random_seed integer not null,
  limitations jsonb not null default '[]',
  provenance jsonb not null default '{}',
  created_at timestamptz not null default now(),
  finished_at timestamptz
);

create table public.delay_study_configurations (
  id uuid primary key,
  campaign_id text not null references public.delay_study_campaigns(id),
  family text not null,
  treatment text not null,
  cca_group text not null,
  capacity_mbps numeric not null check (capacity_mbps > 0),
  queue_packets integer not null check (queue_packets > 0),
  duration_seconds numeric not null check (duration_seconds > 0),
  warmup_seconds numeric not null check (warmup_seconds >= 0 and warmup_seconds < duration_seconds),
  target_rtt_ms numeric,
  config_sha256 text not null,
  unique (campaign_id, config_sha256),
  unique (id, campaign_id)
);
create index on public.delay_study_configurations(campaign_id, family, cca_group, treatment);

create table public.delay_study_config_flows (
  configuration_id uuid not null references public.delay_study_configurations(id),
  flow_index integer not null check (flow_index > 0),
  cca text not null,
  configured_base_rtt_ms numeric not null check (configured_base_rtt_ms >= 0),
  primary key(configuration_id, flow_index)
);

create table public.delay_study_trials (
  id uuid primary key,
  campaign_id text not null references public.delay_study_campaigns(id),
  configuration_id uuid not null,
  block_index integer not null,
  replicate integer not null check (replicate > 0),
  attempt_id text not null,
  status text not null check (status in ('planned','completed','failed','invalid')),
  start_order integer[] not null,
  kernel_release text,
  runner_sha256 text,
  started_at timestamptz,
  finished_at timestamptz,
  validation_errors jsonb not null default '[]',
  cpu_metrics jsonb not null default '[]',
  error text,
  evidence_sha256 text,
  evidence_location text,
  unique(configuration_id, replicate),
  foreign key(configuration_id, campaign_id) references public.delay_study_configurations(id, campaign_id)
);
create index on public.delay_study_trials(campaign_id, status);
create index on public.delay_study_trials(campaign_id, block_index);

create table public.delay_study_flows (
  trial_id uuid not null references public.delay_study_trials(id),
  flow_index integer not null check (flow_index > 0),
  cca text not null,
  configured_base_rtt_ms numeric not null,
  natural_min_rtt_ms numeric,
  added_ack_delay_ms numeric,
  effective_min_rtt_ms numeric,
  goodput_mbps numeric not null check (goodput_mbps >= 0),
  measured_seconds numeric not null check (measured_seconds > 0),
  received_bytes bigint not null check (received_bytes >= 0),
  retransmits bigint,
  primary key(trial_id, flow_index)
);

create table public.delay_study_samples (
  trial_id uuid not null,
  flow_index integer not null,
  snapshot_index integer not null check (snapshot_index >= 0),
  start_seconds numeric not null,
  end_seconds numeric not null,
  interval_seconds numeric not null check (interval_seconds > 0),
  received_bytes bigint not null check (received_bytes >= 0),
  goodput_mbps numeric not null check (goodput_mbps >= 0),
  primary key(trial_id, flow_index, snapshot_index),
  foreign key(trial_id, flow_index) references public.delay_study_flows(trial_id, flow_index)
);

create table public.delay_study_cells (
  configuration_id uuid not null references public.delay_study_configurations(id),
  flow_index integer not null,
  matched_repetitions integer not null check (matched_repetitions >= 0),
  mean_goodput_mbps numeric,
  ci_low_mbps numeric,
  ci_high_mbps numeric,
  mean_share numeric,
  primary key(configuration_id, flow_index),
  foreign key(configuration_id, flow_index) references public.delay_study_config_flows(configuration_id, flow_index)
);

create table public.delay_study_summaries (
  campaign_id text not null references public.delay_study_campaigns(id),
  family text not null,
  cca_group text not null,
  flow_index integer not null,
  cca text not null,
  baseline_delta numeric,
  baseline_ci_low numeric,
  baseline_ci_high numeric,
  treatment_delta numeric,
  treatment_ci_low numeric,
  treatment_ci_high numeric,
  improvement numeric,
  improvement_ci_low numeric,
  improvement_ci_high numeric,
  assessment text not null,
  matched_pairs integer not null,
  expected_pairs integer not null,
  observed_assignments integer not null,
  expected_assignments integer not null,
  unbounded boolean not null default false,
  analysis_sha256 text not null,
  primary key(campaign_id, family, cca_group, flow_index)
);

create table public.delay_study_papers (
  campaign_id text not null references public.delay_study_campaigns(id),
  reference_number integer not null,
  citation text not null,
  kind text not null,
  source_url text,
  download_status text not null,
  reading_status text not null,
  sha256 text,
  pages integer,
  version_note text,
  reading_notes text,
  primary key(campaign_id, reference_number)
);

create table public.delay_study_claims (
  campaign_id text not null references public.delay_study_campaigns(id),
  claim_id text not null,
  figure text not null,
  description text not null,
  published_values jsonb not null default '{}',
  coverage text not null,
  limitation text not null,
  primary key(campaign_id, claim_id)
);

create table public.delay_study_latency_trials (
  campaign_id text not null references public.delay_study_campaigns(id),
  worker_index integer not null,
  treatment text not null,
  sent_packets integer not null,
  received_packets integer not null,
  median_forward_ms numeric not null,
  median_rtt_ms numeric not null,
  validation_passed boolean not null,
  primary key(campaign_id, worker_index, treatment)
);

create table public.delay_study_latency_samples (
  campaign_id text not null,
  worker_index integer not null,
  treatment text not null,
  packet_index integer not null,
  forward_ms numeric not null,
  rtt_ms numeric not null,
  primary key(campaign_id, worker_index, treatment, packet_index),
  foreign key(campaign_id, worker_index, treatment)
    references public.delay_study_latency_trials(campaign_id, worker_index, treatment)
);

do $policy$
declare relation text;
begin
  foreach relation in array array[
    'delay_study_campaigns','delay_study_configurations','delay_study_config_flows',
    'delay_study_trials','delay_study_flows','delay_study_samples','delay_study_cells',
    'delay_study_summaries','delay_study_papers','delay_study_claims',
    'delay_study_latency_trials','delay_study_latency_samples'
  ] loop
    execute format('alter table public.%I enable row level security', relation);
    execute format('revoke all on public.%I from public, anon, authenticated', relation);
    execute format('grant select on public.%I to anon, authenticated', relation);
    execute format('grant all on public.%I to service_role', relation);
    execute format('create policy published_measurements_read on public.%I for select to anon, authenticated using (true)', relation);
  end loop;
end
$policy$;

notify pgrst, 'reload schema';
commit;
