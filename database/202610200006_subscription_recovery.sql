-- Explicit local-only continuation after one verified request rejection.
begin;
create table public.research_subscription_recoveries (
 id uuid primary key,
 pilot_id uuid not null references public.research_subscription_pilots(id),
 rejected_call_id uuid not null unique references public.research_subscription_calls(id),
 protocol_raw bytea not null,
 protocol_sha256 text not null,
 original_report_raw bytea not null,
 original_report_sha256 text not null,
 rejection_sha256 text not null,
 reserved_overhead_cents integer not null check(reserved_overhead_cents=1000),
 receipt jsonb not null,
 created_at timestamptz not null default clock_timestamp(),
 check(encode(sha256(protocol_raw),'hex')=protocol_sha256),
 check(encode(sha256(original_report_raw),'hex')=original_report_sha256)
);
create function public.research_subscription_recovery_guard() returns trigger language plpgsql as $$
declare r public.research_subscription_calls; d jsonb;
begin
 if tg_op<>'INSERT' then raise exception 'Subscription recovery receipts are append only'; end if;
 select * into strict r from public.research_subscription_calls where id=new.rejected_call_id;
 if r.pilot_id<>new.pilot_id or r.status<>'failed' or r.http_status<>400 or
    r.response_raw is null or r.response_sha256<>new.rejection_sha256 then
  raise exception 'Only an exact retained HTTP 400 rejection can be reviewed';
 end if;
 d=convert_from(r.response_raw,'UTF8')::jsonb;
 if d->'error'->>'type' is distinct from 'invalid_request_error' or
    d->'error'->>'param' is distinct from 'input' or
    d->'error'->>'message' is distinct from $m$Response input messages must contain the word 'json' in some form to use 'text.format' of type 'json_object'.$m$ then
  raise exception 'This recovery only covers the recorded missing-JSON-input rejection';
 end if;
 return new;
end $$;
create trigger research_subscription_recovery_guard before insert or update or delete on public.research_subscription_recoveries
 for each row execute function public.research_subscription_recovery_guard();
revoke all on function public.research_subscription_recovery_guard() from public,anon,authenticated;
alter table public.research_subscription_recoveries enable row level security;
revoke all on public.research_subscription_recoveries from public,anon,authenticated;
grant select,insert on public.research_subscription_recoveries to service_role;
commit;
