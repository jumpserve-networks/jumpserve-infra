-- Runs after the migration, within the fixture transaction.
do $$ begin
    if has_table_privilege('anon','public.benchmark_ingest_tokens','select') or
       has_table_privilege('authenticated','public.benchmark_ingest_tokens','select') or
       has_function_privilege('anon','public.benchmark_ingest(uuid,text,text,jsonb)','execute') or
       has_function_privilege('authenticated','public.benchmark_ingest(uuid,text,text,jsonb)','execute') or
       has_table_privilege('authenticated','public.benchmark_jobs','truncate') or
       not (select relrowsecurity from pg_class where oid='public.benchmark_ingest_tokens'::regclass) then
        raise exception 'Ingestion access leaked';
    end if;
end $$;
insert into public.benchmark_jobs(id,status,config) values
('11111111-1111-4111-8111-111111111111','launching','{"num_clients":1,"client_ccas":["cubic"],"client_delays_ms":[10],"client_file_sizes_mbytes":[5],"bottleneck_all_client_rate_mbit":10,"bottleneck_buffer_kbytes":125,"topology":"dumbbell","bottleneck_rates_mbit":[100,50],"bottleneck_buffers_kbytes":[900,800]}'),
('22222222-2222-4222-8222-222222222222','running','{}');
insert into public.benchmark_ingest_tokens(job_id,token_hash) values
('11111111-1111-4111-8111-111111111111',repeat('a',64)),
('22222222-2222-4222-8222-222222222222',repeat('b',64));
create function pg_temp.expect_rejection(target uuid, token text, operation text, payload jsonb) returns void language plpgsql as $$
begin
    perform public.benchmark_ingest(target,token,operation,payload);
    raise exception 'Unexpectedly accepted invalid ingestion';
exception when insufficient_privilege or invalid_parameter_value or not_null_violation or numeric_value_out_of_range then null;
end $$;
set local role service_role;
select pg_temp.expect_rejection('11111111-1111-4111-8111-111111111111',repeat('b',64),'status','{"status":"running"}');
select pg_temp.expect_rejection('22222222-2222-4222-8222-222222222222',repeat('a',64),'status','{"status":"running"}');
select pg_temp.expect_rejection('11111111-1111-4111-8111-111111111111',repeat('a',64),'delete','{}');
select pg_temp.expect_rejection('11111111-1111-4111-8111-111111111111',repeat('a',64),'status','{"status":"completed","parent_run_id":123}');
update public.benchmark_ingest_tokens set expires_at=now()-interval '1 second' where token_hash=repeat('a',64);
select pg_temp.expect_rejection('11111111-1111-4111-8111-111111111111',repeat('a',64),'status','{"status":"running"}');
update public.benchmark_ingest_tokens set expires_at=now()+interval '45 minutes' where token_hash=repeat('a',64);
select public.benchmark_ingest('11111111-1111-4111-8111-111111111111',repeat('a',64),'status','{"status":"running"}');
select public.benchmark_ingest('11111111-1111-4111-8111-111111111111',repeat('a',64),'status','{"status":"installing"}');
do $$ declare
    target uuid := '11111111-1111-4111-8111-111111111111';
    report jsonb := '{"parent":{"number_of_clients":1,"bottleneck_rate_megabit":10,"queue_buffer_size_kilobyte":125,"snapshot_length_ms":100},"algorithms":{"cubic":1},"runs":[{"id":1,"client_number":1,"emulated_parent_run_id":1,"congestion_control_algorithm_id":1,"delay_added":10,"client_file_size_megabytes":5,"client_start_delay_ms":0,"flow_completion_time_ms":500}],"snapshots":[{"emulated_run_id":1,"snapshot_index":0,"elapsed_microseconds":100000,"megabits_per_second":5,"round_trip_time_ms":20,"bottleneck_queuing_delay_ms":10,"bottleneck_backlog_bytes":0,"in_flight_packets":2,"congestion_window_bytes":20000}],"raw_run":null}';
    result jsonb;
begin
    if (select status from public.benchmark_jobs where id=target)<>'running' then raise exception 'Status regressed'; end if;
    perform pg_temp.expect_rejection(target,repeat('a',64),'results',jsonb_set(report,'{runs,0,client_number}','2'));
    perform pg_temp.expect_rejection(target,repeat('a',64),'results',jsonb_set(report,'{runs,0,emulated_parent_run_id}','999'));
    perform pg_temp.expect_rejection(target,repeat('a',64),'results',jsonb_set(report,'{runs,0,delay_added}','60'));
    perform pg_temp.expect_rejection(target,repeat('a',64),'results',jsonb_set(report,'{snapshots,0,emulated_run_id}','999'));
    perform pg_temp.expect_rejection(target,repeat('a',64),'results',jsonb_set(report,'{snapshots,0,congestion_window_bytes}','null'));
    if exists(select 1 from public.emulated_parent_runs) or exists(select 1 from public.emulated_runs) then raise exception 'Invalid report partially persisted'; end if;
    update public.benchmark_jobs set status='cancelled' where id=target;
    perform pg_temp.expect_rejection(target,repeat('a',64),'results',report);
    update public.benchmark_jobs set status='running' where id=target;
    result := public.benchmark_ingest(target,repeat('a',64),'results',report);
    if result is distinct from public.benchmark_ingest(target,repeat('a',64),'results',report) then raise exception 'Retry changed result'; end if;
    perform pg_temp.expect_rejection(target,repeat('a',64),'results',jsonb_set(report,'{runs,0,flow_completion_time_ms}','501'));
    perform pg_temp.expect_rejection(target,repeat('a',64),'status','{"status":"failed"}');
    if (select count(*) from public.emulated_runs)<>1 or (select count(*) from public.emulated_snapshot_stats)<>1 or
       (select parent_run_id from public.benchmark_jobs where id=target) is distinct from (result->>'parent_run_id')::integer or
       (select emulated_run_id from public.emulated_snapshot_stats) is distinct from (result->'run_ids'->>'1')::integer then
        raise exception 'Atomic result linkage failed';
    end if;
    if (select topology from public.emulated_parent_runs)<>'single-bottleneck' or
       (select topology_config from public.emulated_parent_runs) is not null then
        raise exception 'Single-bottleneck result inherited unused topology settings';
    end if;
    insert into public.benchmark_jobs(id,status,config) values
        ('33333333-3333-4333-8333-333333333333','running',
         '{"script":"netem_multi_bottleneck.py","num_clients":1,"client_ccas":["cubic"],"client_delays_ms":[10],"client_file_sizes_mbytes":[5],"bottleneck_all_client_rate_mbit":10,"bottleneck_buffer_kbytes":125,"topology":"parking-lot","bottleneck_rates_mbit":[50,20],"bottleneck_buffers_kbytes":[64,32]}');
    insert into public.benchmark_ingest_tokens(job_id,token_hash) values
        ('33333333-3333-4333-8333-333333333333',repeat('c',64));
    report := jsonb_set(jsonb_set(report,'{parent,bottleneck_rate_megabit}','50'),'{parent,queue_buffer_size_kilobyte}','64');
    result := public.benchmark_ingest('33333333-3333-4333-8333-333333333333',repeat('c',64),'results',report);
    if not exists(select 1 from public.emulated_parent_runs where id=(result->>'parent_run_id')::integer
        and topology='parking-lot' and bottleneck_rate_megabit=50 and queue_buffer_size_kilobyte=64
        and topology_config->'bottleneck_rates_mbit'='[50,20]'::jsonb) then
        raise exception 'Multi-bottleneck result lost its topology';
    end if;
end $$;
select public.benchmark_ingest('22222222-2222-4222-8222-222222222222',repeat('b',64),'status','{"status":"failed","error_message":"expected fixture failure"}');
select pg_temp.expect_rejection('22222222-2222-4222-8222-222222222222',repeat('b',64),'status','{"status":"running"}');
reset role;
rollback;
