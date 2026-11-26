begin;

alter table public.research_skill_instruction_settings
  add column last_version_number integer not null default 0 check (last_version_number >= 0);

alter table public.research_skill_instruction_versions add column version_number integer;

-- The table lock keeps the immutability trigger bypass confined to this backfill.
alter table public.research_skill_instruction_versions disable trigger research_skill_hash_instructions;
with numbered as (
  select role, version_id, row_number() over (partition by role order by created_at, version_id) as version_number
  from public.research_skill_instruction_versions
)
update public.research_skill_instruction_versions v set version_number = n.version_number
from numbered n where (v.role, v.version_id) = (n.role, n.version_id);
alter table public.research_skill_instruction_versions enable trigger research_skill_hash_instructions;

alter table public.research_skill_instruction_versions
  alter column version_number set not null,
  add check (version_number > 0),
  add unique (role, version_number);

update public.research_skill_instruction_settings s set last_version_number = latest.version_number
from (select role, max(version_number) as version_number
      from public.research_skill_instruction_versions group by role) latest
where s.role = latest.role;

create or replace function public.research_skill_hash_instructions()
returns trigger language plpgsql set search_path = '' as $$
begin
  if tg_op <> 'INSERT' then
    raise exception 'Create a new version to change skill instructions' using errcode = '22023';
  end if;
  if new.version_number is not null then
    raise exception 'Skill version numbers are assigned automatically' using errcode = '22023';
  end if;

  -- Updating the role row serializes numbering and rolls it back if insertion fails.
  update public.research_skill_instruction_settings s
    set last_version_number = s.last_version_number + 1
    where s.role = new.role returning s.last_version_number into new.version_number;
  if not found then
    raise exception 'Unknown skill role' using errcode = '22023';
  end if;

  new.sha256 := encode(sha256(convert_to(new.instructions, 'UTF8')), 'hex');
  return new;
end
$$;

drop function public.research_skill_get_instructions(text,uuid);
create function public.research_skill_get_instructions(p_role text, p_version_id uuid default null)
returns table (role text, version_id uuid, sha256 text, instructions text, version_number integer)
language sql stable security definer set search_path = '' as $$
  select v.role, v.version_id, v.sha256, v.instructions, v.version_number
  from public.research_skill_instruction_versions v
  join public.research_skill_instruction_settings s on s.role = v.role
  where v.role = p_role and v.version_id = coalesce(p_version_id, s.active_version_id)
    and exists (select 1 from public.research_skill_instruction_publications p
      where p.role = v.role and p.version_id = v.version_id);
$$;
revoke all on function public.research_skill_get_instructions(text,uuid) from public, anon, authenticated, service_role;
grant execute on function public.research_skill_get_instructions(text,uuid) to service_role;

notify pgrst, 'reload schema';
commit;
