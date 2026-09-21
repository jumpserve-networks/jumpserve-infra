-- Entire test rolls back, including fixtures. Never run against production.
begin;
set local client_min_messages=warning;
do $$ begin
    if current_database()<>'jumpserve_prompt_test' then raise exception 'Wrong test database'; end if;
end $$;
do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
do $$ begin create role service_role bypassrls; exception when duplicate_object then null; end $$;
grant usage on schema public to anon,authenticated,service_role;
create table public.agent_sessions(id uuid primary key);
create table public.benchmark_configs(id uuid primary key);
create table public.benchmark_jobs(id uuid primary key,status text,config jsonb,created_at timestamptz default now(),updated_at timestamptz,parent_run_id bigint,error_message text);
create table public.congestion_control_algorithms(id smallint generated always as identity primary key,name text not null);
create table public.emulated_parent_runs(id integer generated always as identity primary key,number_of_clients smallint not null,bottleneck_rate_megabit numeric not null,queue_buffer_size_kilobyte numeric not null,snapshot_length_ms smallint not null,topology text,topology_config jsonb,tags text[],notes text,experiment_name text);
create table public.emulated_runs(id integer generated always as identity primary key,emulated_parent_run_id integer not null references public.emulated_parent_runs,client_number smallint not null,delay_added smallint not null,congestion_control_algorithm_id smallint not null references public.congestion_control_algorithms,client_file_size_megabytes smallint not null,client_start_delay_ms smallint not null,flow_completion_time_ms integer not null);
create table public.emulated_snapshot_stats(id integer generated always as identity primary key,emulated_run_id integer not null references public.emulated_runs,snapshot_index smallint not null,elapsed_microseconds integer not null,megabits_per_second numeric not null,round_trip_time_ms numeric not null,bottleneck_queuing_delay_ms numeric not null,bottleneck_backlog_bytes integer not null,in_flight_packets integer not null,congestion_window_bytes bigint not null);
create table public.runs(id text primary key,started_at timestamptz not null,ended_at timestamptz,hostname text,runner_version text,delay_added_ms integer,log_path text,raw_log jsonb);
grant all on all tables in schema public to service_role,authenticated;
grant usage,select on all sequences in schema public to service_role;
