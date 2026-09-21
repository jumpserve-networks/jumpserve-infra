-- EC2 runners hold a short-lived job token, never a Supabase credential.
begin;
set local statement_timeout = '60s';

create table if not exists public.benchmark_ingest_tokens (
    job_id uuid primary key references public.benchmark_jobs(id) on delete cascade,
    token_hash text not null check (token_hash ~ '^[a-f0-9]{64}$'),
    expires_at timestamptz not null default (now() + interval '45 minutes'),
    result_hash text,
    result jsonb,
    revoked boolean not null default false
);
alter table public.benchmark_ingest_tokens enable row level security;
revoke all on public.benchmark_ingest_tokens from public, anon, authenticated;
grant select, insert, update, delete on public.benchmark_ingest_tokens to service_role;

-- RLS does not govern TRUNCATE. Browser roles have no use for these privileges.
revoke truncate, references, trigger on public.agent_sessions, public.benchmark_configs,
    public.benchmark_jobs from anon, authenticated;

-- Only the backend may call this function; it deliberately runs as the caller.
-- The job and capability are locked together so cancellation and duplicate
-- submissions cannot create partial reports or attach someone else's run.
create or replace function public.benchmark_ingest(
    target uuid, supplied_hash text, operation text, payload jsonb
) returns jsonb language plpgsql security invoker set search_path = '' as $$
declare
    capability public.benchmark_ingest_tokens%rowtype;
    job public.benchmark_jobs%rowtype;
    parent jsonb;
    row_data jsonb;
    raw_data jsonb;
    run_map jsonb := '{}';
    algo_map jsonb := '{}';
    parent_id integer;
    run_id integer;
    algo_id smallint;
    client_no integer;
    local_id text;
    cca text;
    expected_clients integer;
    seen_clients integer[] := '{}';
    result_digest text;
    result_data jsonb;
    raw_id text;
    next_status text;
    rounding_tolerance numeric;
    phases text[] := array['pending','launching','installing','cloning','running'];
begin
    select * into job from public.benchmark_jobs where id=target for update;
    select * into capability from public.benchmark_ingest_tokens where job_id=target for update;
    if job.id is null or capability.job_id is null or
       supplied_hash is distinct from capability.token_hash or capability.expires_at <= clock_timestamp() then
        raise exception 'Invalid or expired job token' using errcode='42501';
    end if;
    if operation = 'results' then
        result_digest := encode(sha256(convert_to(payload::text,'UTF8')),'hex');
        if capability.result_hash = result_digest and job.status='completed' then
            return capability.result; -- Exact retries are safe, including a lost HTTP response.
        end if;
    end if;
    if capability.revoked or not (job.status=any(phases)) then
        raise exception 'Job no longer accepts updates' using errcode='42501';
    end if;
    if operation = 'status' then
        next_status := payload->>'status';
        if next_status='failed' then
            update public.benchmark_jobs set status='failed',
                error_message=left(payload->>'error_message',500), updated_at=now() where id=target;
            update public.benchmark_ingest_tokens set revoked=true where job_id=target;
        elsif next_status in ('installing','cloning','running') then
            if array_position(phases,next_status) >= array_position(phases,job.status) then
                update public.benchmark_jobs set status=next_status, updated_at=now() where id=target;
            end if;
        else
            raise exception 'Invalid status' using errcode='22023';
        end if;
        return jsonb_build_object('accepted',true);
    end if;
    if operation is distinct from 'results' then
        raise exception 'Unsupported ingestion operation' using errcode='22023';
    end if;
    expected_clients := (job.config->>'num_clients')::integer;
    -- Existing schemas store integer milliseconds/MB: base runners round while
    -- the multi-bottleneck runner truncates. Preserve that measurement contract.
    rounding_tolerance := case when job.config->>'script'='netem_multi_bottleneck.py' then 0.999999 else 0.5 end;
    parent := payload->'parent';
    if jsonb_typeof(parent) is distinct from 'object' or
       jsonb_typeof(payload->'runs') is distinct from 'array' or
       jsonb_typeof(payload->'snapshots') is distinct from 'array' or
       jsonb_typeof(payload->'algorithms') is distinct from 'object' then
        raise exception 'Invalid result report' using errcode='22023';
    end if;
    if expected_clients not between 1 and 10 or
       (parent->>'number_of_clients')::integer is distinct from expected_clients or
       jsonb_array_length(payload->'runs') <> expected_clients or
       jsonb_array_length(payload->'snapshots') > 200000 or
       octet_length(payload::text)>33554432 or
       (parent->>'snapshot_length_ms')::integer not between 1 and 32767 then
        raise exception 'Report size or client count invalid' using errcode='22023';
    end if;
    if (parent->>'bottleneck_rate_megabit')::numeric is distinct from
        coalesce((job.config->'bottleneck_rates_mbit'->>0)::numeric,(job.config->>'bottleneck_all_client_rate_mbit')::numeric) or
       (parent->>'queue_buffer_size_kilobyte')::numeric is distinct from
        coalesce((job.config->'bottleneck_buffers_kbytes'->>0)::numeric,(job.config->>'bottleneck_buffer_kbytes')::numeric) then
        raise exception 'Report configuration does not match job' using errcode='22023';
    end if;
    insert into public.emulated_parent_runs(number_of_clients,bottleneck_rate_megabit,
        queue_buffer_size_kilobyte,snapshot_length_ms,topology,topology_config,tags,notes,experiment_name)
    values(expected_clients,(parent->>'bottleneck_rate_megabit')::numeric,
        (parent->>'queue_buffer_size_kilobyte')::numeric,(parent->>'snapshot_length_ms')::smallint,
        coalesce(job.config->>'topology','single-bottleneck'),
        case when job.config ? 'topology' then jsonb_build_object('topology',job.config->'topology',
            'bottleneck_rates_mbit',job.config->'bottleneck_rates_mbit',
            'bottleneck_buffers_kbytes',job.config->'bottleneck_buffers_kbytes','client_groups',job.config->'client_groups') end,
        array(select jsonb_array_elements_text(coalesce(job.config->'tags','[]'::jsonb))),
        job.config->>'notes',job.config->>'experiment_name') returning id into parent_id;
    for row_data in select value from jsonb_array_elements(payload->'runs') loop
        local_id := row_data->>'id';
        client_no := (row_data->>'client_number')::integer;
        cca := job.config->'client_ccas'->>(client_no-1);
        if local_id is null or local_id !~ '^[1-9][0-9]?$' or run_map ? local_id or
           client_no is null or client_no not between 1 and expected_clients or client_no=any(seen_clients) or
           cca is null or cca !~ '^[a-z][a-z0-9_]{0,31}$' or
           payload->'algorithms'->cca is distinct from row_data->'congestion_control_algorithm_id' or
           (row_data->>'emulated_parent_run_id')::integer is distinct from 1 or
           abs((row_data->>'delay_added')::numeric-(job.config->'client_delays_ms'->>(client_no-1))::numeric)>rounding_tolerance or
           abs((row_data->>'client_file_size_megabytes')::numeric-(job.config->'client_file_sizes_mbytes'->>(client_no-1))::numeric)>rounding_tolerance or
           abs((row_data->>'client_start_delay_ms')::numeric-coalesce((job.config->'client_start_delays_ms'->>(client_no-1))::numeric,0))>rounding_tolerance or
           (row_data->>'flow_completion_time_ms')::integer < 0 then
            raise exception 'Invalid client result or configuration' using errcode='22023';
        end if;
        seen_clients := array_append(seen_clients,client_no);
        select id into algo_id from public.congestion_control_algorithms where name=cca order by id limit 1;
        if algo_id is null then
            insert into public.congestion_control_algorithms(name) values(cca) returning id into algo_id;
        end if;
        algo_map := algo_map || jsonb_build_object(cca,algo_id);
        insert into public.emulated_runs(emulated_parent_run_id,client_number,delay_added,
            congestion_control_algorithm_id,client_file_size_megabytes,client_start_delay_ms,flow_completion_time_ms)
        values(parent_id,client_no,(row_data->>'delay_added')::smallint,algo_id,
            (row_data->>'client_file_size_megabytes')::smallint,(row_data->>'client_start_delay_ms')::smallint,
            (row_data->>'flow_completion_time_ms')::integer) returning id into run_id;
        run_map := run_map || jsonb_build_object(local_id,run_id);
    end loop;
    if exists(select 1 from jsonb_array_elements(payload->'snapshots') s
        where not (run_map ? (s->>'emulated_run_id')) or s->>'emulated_run_id' is null) then
        raise exception 'Snapshot references a foreign run' using errcode='22023';
    end if;
    insert into public.emulated_snapshot_stats(emulated_run_id,snapshot_index,elapsed_microseconds,
        megabits_per_second,round_trip_time_ms,bottleneck_queuing_delay_ms,bottleneck_backlog_bytes,
        in_flight_packets,congestion_window_bytes)
    select (run_map->>s.emulated_run_id::text)::integer,s.snapshot_index,s.elapsed_microseconds,
        s.megabits_per_second,s.round_trip_time_ms,s.bottleneck_queuing_delay_ms,s.bottleneck_backlog_bytes,
        s.in_flight_packets,s.congestion_window_bytes
    from jsonb_to_recordset(payload->'snapshots') as s(emulated_run_id integer,snapshot_index smallint,
        elapsed_microseconds integer,megabits_per_second numeric,round_trip_time_ms numeric,
        bottleneck_queuing_delay_ms numeric,bottleneck_backlog_bytes integer,in_flight_packets integer,congestion_window_bytes bigint);
    raw_data := payload->'raw_run';
    if raw_data is not null and raw_data <> 'null'::jsonb then
        raw_id := gen_random_uuid()::text;
        insert into public.runs(id,started_at,ended_at,hostname,runner_version,delay_added_ms,log_path,raw_log)
        values(raw_id,(raw_data->>'started_at')::timestamptz,(raw_data->>'ended_at')::timestamptz,
            left(raw_data->>'hostname',255),left(raw_data->>'runner_version',255),
            (raw_data->>'delay_added_ms')::integer,left(raw_data->>'log_path',1024),raw_data->'raw_log');
    end if;
    result_data := jsonb_build_object('parent_run_id',parent_id,'run_ids',run_map,'algorithm_ids',algo_map,'raw_run_id',raw_id);
    update public.benchmark_jobs set parent_run_id=parent_id,status='completed',updated_at=now() where id=target;
    update public.benchmark_ingest_tokens set result_hash=result_digest,result=result_data,revoked=true where job_id=target;
    return result_data;
end $$;
revoke all on function public.benchmark_ingest(uuid,text,text,jsonb) from public,anon,authenticated;
grant execute on function public.benchmark_ingest(uuid,text,text,jsonb) to service_role;
commit;
