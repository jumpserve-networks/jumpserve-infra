-- Record lifecycle timings in the same transaction as each public checkpoint.
begin;
set local statement_timeout = '60s';
lock table public.real_world_runs in share row exclusive mode;

create table if not exists public.real_world_status_history (
    id bigint generated always as identity primary key,
    job_id uuid not null references public.real_world_runs(job_id) on delete cascade,
    status text not null,
    started_at timestamptz,
    completed_at timestamptz,
    outcome text check (outcome in ('completed','failed','cancelled')),
    recorded_at timestamptz not null default clock_timestamp(),
    check (completed_at is null or started_at is null or completed_at >= started_at)
);
create index if not exists real_world_status_history_job on public.real_world_status_history(job_id,id);
create unique index if not exists real_world_status_history_current on public.real_world_status_history(job_id)
    where completed_at is null and outcome is null;

alter table public.real_world_status_history enable row level security;
revoke all on public.real_world_status_history from public,anon,authenticated;
grant all on public.real_world_status_history to service_role;
revoke all on sequence public.real_world_status_history_id_seq from public,anon,authenticated;
grant usage,select on sequence public.real_world_status_history_id_seq to service_role;
drop policy if exists jumpserve_require_signed_in_user on public.real_world_status_history;
create policy jumpserve_require_signed_in_user on public.real_world_status_history as restrictive for all to authenticated
    using (auth.uid() is not null and auth.jwt()->>'is_anonymous' is distinct from 'true')
    with check (auth.uid() is not null and auth.jwt()->>'is_anonymous' is distinct from 'true');
drop policy if exists jumpserve_public_results on public.real_world_status_history;
create policy jumpserve_public_results on public.real_world_status_history for select to anon,authenticated using (true);
grant select on public.real_world_status_history to anon,authenticated;

-- Old checkpoints establish the known state, not an invented transition time.
insert into public.real_world_status_history(job_id,status,outcome)
    select job_id,status,case when status in ('completed','failed','cancelled') then status end
    from public.real_world_runs r where not exists (
        select 1 from public.real_world_status_history h where h.job_id=r.job_id);

create or replace function public.real_world_record_status() returns trigger
language plpgsql security invoker set search_path='' as $$
declare stamp timestamptz := clock_timestamp(); next_status text := new.record->>'status';
begin
    if tg_op='UPDATE' then
        if old.record->>'status' is not distinct from next_status then return new; end if;
        update public.real_world_status_history set completed_at=stamp,
            outcome=case
                when old.record->>'status'<>'cleaning' and next_status in ('cleaning','failed','cancelled')
                    and coalesce(new.record->>'outcome',next_status) in ('failed','cancelled')
                    then coalesce(new.record->>'outcome',next_status)
                else 'completed' end
            where job_id=new.job_id and completed_at is null and outcome is null;
    end if;
    insert into public.real_world_status_history(job_id,status,started_at,completed_at,outcome,recorded_at)
        values(new.job_id,next_status,
            case when tg_op='UPDATE' or next_status='provisioning' then stamp end,
            case when tg_op='UPDATE' and next_status in ('completed','failed','cancelled') then stamp end,
            case when next_status in ('completed','failed','cancelled') then next_status end,stamp);
    return new;
end $$;
revoke all on function public.real_world_record_status() from public,anon,authenticated;
grant execute on function public.real_world_record_status() to service_role;
drop trigger if exists real_world_status_changed on public.real_world_runs;
create trigger real_world_status_changed after insert or update of record on public.real_world_runs
    for each row execute function public.real_world_record_status();

notify pgrst,'reload schema';
commit;
