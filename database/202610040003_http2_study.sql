-- Versioned HTTP/2 evidence. Raw author worker payloads remain backend-only.
begin;
create table public.http2_study_protocols (
 id text primary key, version integer not null check(version>0), stage text not null,
 document jsonb not null, sha256 text not null check(length(sha256)=64),
 code_sha256 text, locked_at timestamptz, created_at timestamptz not null default now()
);
create table public.http2_study_campaigns (
 id text primary key references public.http2_study_protocols(id), title text not null,
 status text not null check(status in ('running','complete','partial','failed')),
 protocol jsonb not null, protocol_sha256 text not null check(length(protocol_sha256)=64),
 artifact_commit text not null, analysis_sha256 text not null,
 planned_runs integer not null check(planned_runs>=0), recorded_runs integer not null check(recorded_runs>=0),
 planned_measurements integer not null check(planned_measurements>=0),
 limitations jsonb not null, provenance jsonb not null, costs jsonb not null,
 created_at timestamptz not null default now()
);
create table public.http2_study_configurations (
 campaign_id text not null references public.http2_study_campaigns(id), id text not null,
 proxy text not null, version text, mode text not null check(mode in ('H2EE','H2H1','endpoint')),
 tls boolean, details jsonb not null, requested_resources jsonb, actual_resources jsonb,
 primary key(campaign_id,id)
);
create table public.http2_study_runs (
 campaign_id text not null references public.http2_study_campaigns(id), id text not null,
 configuration_id text, protocol_id text not null references public.http2_study_protocols(id),
 stage text not null, status text not null check(status in ('complete','failed','invalid','excluded','partial')),
 reason text, source_path text, raw_sha256 text, analysis_sha256 text, analysis_version text not null,
 started_at timestamptz, ended_at timestamptz, original_execution_at timestamptz,
 wall_seconds numeric check(wall_seconds>=0), units text not null,
 primary key(campaign_id,id),
 foreign key(campaign_id,configuration_id) references public.http2_study_configurations(campaign_id,id)
);
create table public.http2_study_measurements (
 campaign_id text not null, run_id text not null, test_id integer not null check(test_id between 1 and 156),
 side text not null check(side in ('client','server')), description text not null, rfc_section text,
 expected text not null, expected_scope text, author_outcome text not null, outcome text not null,
 status text not null check(status in ('recorded','ambiguous','missing','excluded')), reason text,
 error_code integer check(error_code>=0), observed_scope text, scope_compatible boolean,
 author_rule_conformant boolean, preserved_rule_conformant boolean,
 primary key(campaign_id,run_id,test_id), foreign key(campaign_id,run_id) references public.http2_study_runs(campaign_id,id),
 check(outcome<>'unknown' or preserved_rule_conformant is null)
);
create table public.http2_study_summaries (
 campaign_id text not null, run_id text not null, configuration_id text not null,
 planned integer not null check(planned in (78,156)), recorded integer not null check(recorded between 0 and planned),
 missing integer not null check(missing between 0 and planned), unknown integer not null check(unknown between 0 and planned),
 recoded integer not null check(recoded between 0 and planned), author_counts jsonb not null, preserved_counts jsonb not null,
 published_counts jsonb, published_source text, assessment text not null,
 differences jsonb not null, scope_observed integer not null, scope_mismatches integer not null, scope_compatible integer not null,
 comparisons jsonb not null, primary key(campaign_id,run_id),
 foreign key(campaign_id,run_id) references public.http2_study_runs(campaign_id,id),
 foreign key(campaign_id,configuration_id) references public.http2_study_configurations(campaign_id,id)
);
create table public.http2_study_sources (
 campaign_id text not null references public.http2_study_campaigns(id), reference_number integer not null check(reference_number between 0 and 48),
 citation text not null, doi text, kind text not null, source_url text, retrieved_url text,
 download_status text not null, review_status text not null check(review_status in ('complete','partial','unreviewed','unavailable')),
 retrieved_version text, sha256 text, pages integer, findings text, limitations text, retrieval_audit jsonb not null,
 primary key(campaign_id,reference_number)
);
create table public.http2_study_claims (
 campaign_id text not null references public.http2_study_campaigns(id), claim_id text not null, location text not null,
 description text not null, assessment text not null check(assessment in ('reproduced','discrepant','inconclusive','untested')),
 evidence text not null, limitation text not null, primary key(campaign_id,claim_id)
);
create table public.http2_study_followups (
 id text primary key references public.http2_study_protocols(id), campaign_id text not null references public.http2_study_campaigns(id),
 stage text not null, provenance jsonb not null, processes jsonb not null, planned integer not null,
 recorded integer not null, summary jsonb not null, costs jsonb not null
);
create table public.http2_study_frame_measurements (
 followup_id text not null references public.http2_study_followups(id), id text not null, replication integer not null,
 case_name text not null, window_seconds numeric not null, expected text not null, expected_error_code integer,
 outcome text, error_code integer, status text not null, reason text, agrees boolean,
 started_at timestamptz, ended_at timestamptz, elapsed_seconds numeric, raw_sha256 text not null,
 -- Only our non-sensitive loopback trace is public, not author worker payloads.
 trace jsonb not null, primary key(followup_id,id)
);
create table public.http2_study_artifacts (
 campaign_id text not null references public.http2_study_campaigns(id), id text not null, sha256 text not null,
 source_path text not null, byte_count bigint not null check(byte_count>=0), payload jsonb not null,
 primary key(campaign_id,id)
);
create index http2_measurement_run on public.http2_study_measurements(campaign_id,run_id,test_id);
create index http2_summary_config on public.http2_study_summaries(campaign_id,configuration_id);
do $security$
declare relation text;
begin
 foreach relation in array array['http2_study_protocols','http2_study_campaigns','http2_study_configurations','http2_study_runs','http2_study_measurements','http2_study_summaries','http2_study_sources','http2_study_claims','http2_study_followups','http2_study_frame_measurements'] loop
  execute format('alter table public.%I enable row level security',relation);
  execute format('revoke all on public.%I from anon,authenticated',relation);
  execute format('grant select on public.%I to anon,authenticated',relation);
  execute format('grant all on public.%I to service_role',relation);
  execute format('create policy http2_public_read on public.%I for select to anon,authenticated using(true)',relation);
  execute format('drop policy if exists jumpserve_require_signed_in_user on public.%I',relation);
  execute format('create policy jumpserve_require_signed_in_user on public.%I as restrictive for all to authenticated using ((select auth.uid()) is not null and (select auth.jwt()->>''is_anonymous'') is distinct from ''true'') with check ((select auth.uid()) is not null and (select auth.jwt()->>''is_anonymous'') is distinct from ''true'')',relation);
 end loop;
end $security$;
alter table public.http2_study_artifacts enable row level security;
revoke all on public.http2_study_artifacts from anon,authenticated;
grant all on public.http2_study_artifacts to service_role;
alter table public.agent_prompt_versions drop constraint agent_prompt_versions_module_id_check;
alter table public.agent_prompt_versions add constraint agent_prompt_versions_module_id_check check(module_id in ('congestion-control-emulated','congestion-control-real-world','leo-emergency-failover','http2-compliance-study'));
alter table public.agent_prompt_settings drop constraint agent_prompt_settings_module_id_check;
alter table public.agent_prompt_settings add constraint agent_prompt_settings_module_id_check check(module_id in ('congestion-control-emulated','congestion-control-real-world','leo-emergency-failover','http2-compliance-study'));
alter table public.agent_sessions drop constraint agent_sessions_module_id_check;
alter table public.agent_sessions add constraint agent_sessions_module_id_check check(module_id in ('congestion-control-emulated','congestion-control-real-world','leo-emergency-failover','http2-compliance-study'));
insert into public.agent_prompt_settings(module_id) values('http2-compliance-study') on conflict(module_id) do nothing;
notify pgrst,'reload schema';
commit;
