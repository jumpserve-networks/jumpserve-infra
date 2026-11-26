-- Run in an isolated database after applying the original skill instructions migration.
insert into public.research_skill_instruction_versions(role, version_id, instructions, created_at)
select 'generator', fixture.id, fixture.instructions, v.created_at + interval '1 second'
from public.research_skill_instruction_versions v
cross join (values
  ('00000000-0000-4000-8000-000000000002'::uuid, 'A published legacy revision'),
  ('00000000-0000-4000-8000-000000000001'::uuid, 'An unpublished legacy revision')
) as fixture(id, instructions)
where v.role = 'generator';

select public.research_skill_activate_instructions(v.role, v.version_id, v.sha256, s.active_version_id)
from public.research_skill_instruction_versions v join public.research_skill_instruction_settings s using (role)
where v.version_id = '00000000-0000-4000-8000-000000000002';

create temp table pre_migration_revisions as select * from public.research_skill_instruction_versions;
create temp table pre_migration_publications as select * from public.research_skill_instruction_publications;

\ir ../database/202611260001_jumpserve_skill_version_numbers.sql

begin;

do $$
declare
  new_number integer;
begin
  if exists (select * from pre_migration_revisions except
      select role, version_id, instructions, sha256, created_at from public.research_skill_instruction_versions)
    or exists (select * from pre_migration_publications except
      select * from public.research_skill_instruction_publications) then
    raise exception 'Backfill changed revision metadata or publication history';
  end if;

  if not exists (select from public.research_skill_instruction_versions
      where version_id = '00000000-0000-4000-8000-000000000001' and version_number = 2)
    or not exists (select from public.research_skill_get_instructions('generator')
      where version_id = '00000000-0000-4000-8000-000000000002' and version_number = 3)
    or exists (select from public.research_skill_get_instructions('generator', '00000000-0000-4000-8000-000000000001'))
    or not exists (select from public.research_skill_get_instructions('coach') where version_number = 1)
    or not exists (select from public.research_skill_get_instructions('verifier') where version_number = 1) then
    raise exception 'Backfill broke ordering, role numbering, or draft visibility';
  end if;

  begin
    insert into public.research_skill_instruction_versions(role, instructions, version_number)
    values ('generator', 'Attempt to set the number explicitly', 40);
    raise exception 'A caller supplied its own version number';
  exception when invalid_parameter_value then null;
  end;

  begin
    insert into public.research_skill_instruction_versions(role, instructions) values ('generator', '');
    raise exception 'Accepted empty instructions';
  exception when check_violation then null;
  end;

  insert into public.research_skill_instruction_versions(role, instructions) values ('generator', 'Next Generator draft')
    returning version_number into strict new_number;
  if new_number <> 4 then raise exception 'Expected Generator version 4'; end if;
  insert into public.research_skill_instruction_versions(role, instructions) values ('verifier', 'Next Verifier draft')
    returning version_number into strict new_number;
  if new_number <> 2 then raise exception 'Expected Verifier version 2'; end if;
  insert into public.research_skill_instruction_versions(role, instructions) values ('coach', 'Next Coach draft')
    returning version_number into strict new_number;
  if new_number <> 2 then raise exception 'Expected Coach version 2'; end if;

  begin
    update public.research_skill_instruction_versions set version_number = 99
    where role = 'generator' and version_number = 4;
    raise exception 'A version number was changed';
  exception when invalid_parameter_value then null;
  end;
end
$$;

rollback;
