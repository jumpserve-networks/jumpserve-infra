begin;

-- The verified project had no public.profiles relation before this migration.
-- Identity and measurements remain in their existing tables; these are private
-- preferences only. No auth metadata or other users' profiles are exposed.
create function public.profile_timezone_valid(value text) returns boolean
language sql stable set search_path = '' as $$
  select value is null or exists(select 1 from pg_catalog.pg_timezone_names where name = value)
$$;
revoke all on function public.profile_timezone_valid(text) from public, anon;
grant execute on function public.profile_timezone_valid(text) to authenticated, service_role;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  first_name text not null default '' check (char_length(first_name) <= 100 and first_name !~ '[[:cntrl:]]'),
  last_name text not null default '' check (char_length(last_name) <= 100 and last_name !~ '[[:cntrl:]]'),
  timezone text check (char_length(timezone) <= 100 and public.profile_timezone_valid(timezone))
);
alter table public.profiles enable row level security;
revoke all on table public.profiles from public, anon, authenticated;
grant select (id, first_name, last_name, timezone), insert (id, first_name, last_name, timezone),
  update (id, first_name, last_name, timezone) on public.profiles to authenticated;
grant all on public.profiles to service_role;

create policy profile_owner_read on public.profiles for select to authenticated using ((select auth.uid()) = id);
create policy profile_owner_insert on public.profiles for insert to authenticated with check ((select auth.uid()) = id);
create policy profile_owner_update on public.profiles for update to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

comment on column public.profiles.timezone is 'IANA time zone preference; null uses the browser time zone. Recorded measurement timestamps retain their original instants.';
commit;
