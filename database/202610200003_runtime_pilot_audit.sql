-- Lab pilot audit. Apply locally for the development campaign; no public API.
begin;
create table public.research_runtime_pilots (
 id uuid primary key,
 protocol_raw bytea not null,
 protocol_sha256 text not null check (protocol_sha256 ~ '^[0-9a-f]{64}$'),
 configuration jsonb not null,
 started_at timestamptz,
 ended_at timestamptz,
 status text not null check(status in ('prepared','running','complete','failed','limited')),
 maximum_cents integer not null check(maximum_cents between 1 and 10000),
 overhead_cents integer not null check(overhead_cents >= 0),
 report jsonb,
 check(encode(sha256(protocol_raw),'hex')=protocol_sha256)
);
create table public.research_runtime_pilot_calls (
 id uuid primary key,
 pilot_id uuid not null references public.research_runtime_pilots(id),
 arm text not null check(arm in ('jumpserve-direct','openclaw-runtime')),
 number integer not null check(number between 1 and 25),
 logical_request_sha256 text not null,
 request_raw bytea not null,
 request_sha256 text not null,
 transport_raw bytea,
 transport_sha256 text,
 response_raw bytea,
 response_sha256 text,
 status text not null check(status in ('running','complete','failed','unknown')),
 reserved_cents integer not null check(reserved_cents > 0),
 estimated_cents integer,
 usage jsonb,
 started_at timestamptz not null default clock_timestamp(),
 ended_at timestamptz,
 reason text,
 unique(pilot_id,arm,number),
 unique(pilot_id,arm,request_sha256),
 check(encode(sha256(request_raw),'hex')=request_sha256),
 check((transport_raw is null and transport_sha256 is null) or encode(sha256(transport_raw),'hex')=transport_sha256),
 check((response_raw is null and response_sha256 is null) or encode(sha256(response_raw),'hex')=response_sha256)
);
create function public.research_runtime_pilot_immutable() returns trigger language plpgsql as $$
begin
 if tg_table_name='research_runtime_pilots' then
  if (to_jsonb(new)-array['status','report','started_at','ended_at']) is distinct from (to_jsonb(old)-array['status','report','started_at','ended_at']) then
   raise exception 'Frozen pilot protocol and configuration are immutable';
  end if;
 else
  if (to_jsonb(new)-array['status','response_raw','response_sha256','usage','estimated_cents','ended_at','reason']) is distinct from (to_jsonb(old)-array['status','response_raw','response_sha256','usage','estimated_cents','ended_at','reason']) then
   raise exception 'Original provider request and commitment are immutable';
  end if;
  if old.response_raw is not null and (new.response_raw is distinct from old.response_raw or new.response_sha256 is distinct from old.response_sha256) then
   raise exception 'Original provider response is immutable';
  end if;
 end if;
 return new;
end $$;
create trigger research_runtime_pilot_immutable before update on public.research_runtime_pilots for each row execute function public.research_runtime_pilot_immutable();
create trigger research_runtime_pilot_call_immutable before update on public.research_runtime_pilot_calls for each row execute function public.research_runtime_pilot_immutable();
revoke all on function public.research_runtime_pilot_immutable() from public,anon,authenticated;
alter table public.research_runtime_pilots enable row level security;
alter table public.research_runtime_pilot_calls enable row level security;
revoke all on public.research_runtime_pilots,public.research_runtime_pilot_calls from public,anon,authenticated;
grant select,insert,update on public.research_runtime_pilots,public.research_runtime_pilot_calls to service_role;
commit;
