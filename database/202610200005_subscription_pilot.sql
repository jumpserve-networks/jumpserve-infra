-- Private local lab evidence for subscription-backed model turns. No public API.
begin;
create table public.research_subscription_pilots (
 id uuid primary key,
 study_id uuid not null references public.research_studies(id),
 protocol_raw bytea not null,
 protocol_sha256 text not null,
 configuration jsonb not null,
 prior_committed_cents integer not null check(prior_committed_cents >= 0),
 overhead_cents integer not null check(overhead_cents >= 0),
 maximum_cents integer not null check(maximum_cents between 1 and 10000),
 status text not null check(status in ('prepared','running','complete','paused','failed','limited')),
 started_at timestamptz,
 ended_at timestamptz,
 reason text,
 report jsonb,
 check(encode(sha256(protocol_raw),'hex')=protocol_sha256),
 check(prior_committed_cents+overhead_cents<=maximum_cents)
);
create table public.research_subscription_calls (
 id uuid primary key,
 pilot_id uuid not null references public.research_subscription_pilots(id),
 number integer not null check(number between 1 and 25),
 logical_raw bytea not null,
 logical_sha256 text not null,
 request_raw bytea not null,
 request_sha256 text not null,
 transport_raw bytea not null,
 transport_sha256 text not null,
 response_raw bytea,
 response_sha256 text,
 status text not null check(status in ('running','complete','paused-quota','paused-auth','failed','unknown','invalid-output')),
 reserved_cents integer not null check(reserved_cents>0),
 usage jsonb,
 estimated_cents integer,
 http_status integer,
 error_code text,
 request_id text,
 started_at timestamptz not null default clock_timestamp(),
 ended_at timestamptz,
 unique(pilot_id,number),
 unique(pilot_id,request_sha256),
 check(encode(sha256(logical_raw),'hex')=logical_sha256),
 check(encode(sha256(request_raw),'hex')=request_sha256),
 check(encode(sha256(transport_raw),'hex')=transport_sha256),
 check((response_raw is null and response_sha256 is null) or
       (response_raw is not null and response_sha256 is not null and encode(sha256(response_raw),'hex')=response_sha256)),
 -- Subscription allocation is unavailable; API list prices are not its cost.
 check(estimated_cents is null)
);
create function public.research_subscription_immutable() returns trigger language plpgsql as $$
begin
 if tg_op='DELETE' then raise exception 'Subscription evidence cannot be deleted'; end if;
 if tg_table_name='research_subscription_pilots' then
  if (to_jsonb(new)-array['status','started_at','ended_at','reason','report']) is distinct from
     (to_jsonb(old)-array['status','started_at','ended_at','reason','report']) then
   raise exception 'Frozen subscription protocol and configuration are immutable';
  end if;
 else
  if old.status<>'running' or
     (to_jsonb(new)-array['status','response_raw','response_sha256','usage','http_status','error_code','request_id','ended_at']) is distinct from
     (to_jsonb(old)-array['status','response_raw','response_sha256','usage','http_status','error_code','request_id','ended_at']) then
   raise exception 'Original subscription turn and terminal receipt are immutable';
  end if;
 end if;
 return new;
end $$;
create trigger research_subscription_pilot_immutable before update or delete on public.research_subscription_pilots
 for each row execute function public.research_subscription_immutable();
create trigger research_subscription_call_immutable before update or delete on public.research_subscription_calls
 for each row execute function public.research_subscription_immutable();
revoke all on function public.research_subscription_immutable() from public,anon,authenticated;
alter table public.research_subscription_pilots enable row level security;
alter table public.research_subscription_calls enable row level security;
revoke all on public.research_subscription_pilots,public.research_subscription_calls from public,anon,authenticated;
grant select,insert,update on public.research_subscription_pilots,public.research_subscription_calls to service_role;
commit;
