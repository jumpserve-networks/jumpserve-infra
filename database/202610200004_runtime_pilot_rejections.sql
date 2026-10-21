-- Explicit-rejection receipts for a local, exposed operational follow-up.
begin;
alter table public.research_runtime_pilot_calls drop constraint research_runtime_pilot_calls_status_check;
alter table public.research_runtime_pilot_calls add constraint research_runtime_pilot_calls_status_check
 check(status in ('running','complete','failed','unknown','rejected'));
create table public.research_runtime_pilot_amendments (
 id uuid primary key,
 pilot_id uuid not null references public.research_runtime_pilots(id),
 protocol_raw bytea not null,
 protocol_sha256 text not null,
 original_report_raw bytea not null,
 original_report_sha256 text not null,
 receipt jsonb not null,
 created_at timestamptz not null default clock_timestamp(),
 check(encode(sha256(protocol_raw),'hex')=protocol_sha256),
 check(encode(sha256(original_report_raw),'hex')=original_report_sha256)
);
alter table public.research_runtime_pilot_amendments enable row level security;
revoke all on public.research_runtime_pilot_amendments from public,anon,authenticated;
grant select,insert on public.research_runtime_pilot_amendments to service_role;
create function public.research_runtime_pilot_append_only() returns trigger language plpgsql as $$
begin raise exception 'Original pilot amendments and rejection receipts are append only'; end $$;
create trigger research_runtime_pilot_amendments_immutable before update or delete on public.research_runtime_pilot_amendments
 for each row execute function public.research_runtime_pilot_append_only();
revoke all on function public.research_runtime_pilot_append_only() from public,anon,authenticated;
commit;
