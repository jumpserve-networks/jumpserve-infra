-- Public experiment reads; test execution, saved configurations and AI remain authenticated.
-- Apply after 202609200002_authenticated_table_access.sql. RLS stays enabled.
begin;
set local statement_timeout = '60s';
grant usage on schema public to anon;

do $$
declare table_name text;
begin
    foreach table_name in array array[
        'congestion_control_algorithms', 'emulated_parent_runs', 'emulated_runs',
        'emulated_snapshot_stats', 'benchmark_jobs'
    ] loop
        execute format('alter table public.%I enable row level security', table_name);
        execute format('drop policy if exists jumpserve_require_signed_in_user on public.%I', table_name);
        -- Authenticated sessions still need a real user, including for writes.
        execute format('create policy jumpserve_require_signed_in_user on public.%I as restrictive for all to authenticated
            using (auth.uid() is not null and auth.jwt()->>''is_anonymous'' is distinct from ''true'')
            with check (auth.uid() is not null and auth.jwt()->>''is_anonymous'' is distinct from ''true'')', table_name);
        execute format('drop policy if exists jumpserve_public_results on public.%I', table_name);
        execute format('create policy jumpserve_public_results on public.%I for select to anon using (true)', table_name);
        execute format('revoke all on public.%I from anon', table_name);
        if table_name <> 'benchmark_jobs' then
            execute format('grant select on public.%I to anon', table_name);
        end if;
    end loop;
end $$;

-- Benchmark provenance is needed for valid comparisons. Do not expose requester emails.
grant select (id, created_at, updated_at, status, config, ec2_instance_id, parent_run_id, error_message)
    on public.benchmark_jobs to anon;

-- Private tables, RPCs, sequences, and the default-deny new-table guard are unchanged.
notify pgrst, 'reload schema';
commit;
