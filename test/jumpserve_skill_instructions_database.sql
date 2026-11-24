-- Run against an isolated PostgreSQL database after applying the migration.
begin;

do $$
declare
  baseline record;
  draft record;
  content text := E'Synthetic candidate with exact UTF-8 bytes.\nA café reference.\n';
begin
  if (select count(*) from public.research_skill_instruction_settings where active_version_id is not null) <> 3 then
    raise exception 'Expected three active seed versions';
  end if;
  select * into strict baseline from public.research_skill_get_instructions('coach');
  insert into public.research_skill_instruction_versions(role, instructions) values ('coach', content)
    returning version_id, sha256 into draft;
  if draft.sha256 <> encode(sha256(convert_to(content, 'UTF8')), 'hex') then
    raise exception 'Mismatched instruction checksum';
  end if;
  if exists (select 1 from public.research_skill_get_instructions('coach', draft.version_id)) then
    raise exception 'Draft visible by ID';
  end if;
  begin
    update public.research_skill_instruction_versions set instructions = 'Changed' where version_id = draft.version_id;
    raise exception 'An instruction version was overwritten';
  exception when invalid_parameter_value then null;
  end;
  begin
    delete from public.research_skill_instruction_versions where version_id = draft.version_id;
    raise exception 'An instruction version was deleted';
  exception when invalid_parameter_value then null;
  end;
  begin
    perform public.research_skill_activate_instructions('coach', draft.version_id, repeat('a', 64), baseline.version_id);
    raise exception 'Activated the wrong checksum';
  exception when invalid_parameter_value then null;
  end;
  begin
    perform public.research_skill_activate_instructions('coach', draft.version_id, draft.sha256, null);
    raise exception 'Activated from a stale baseline';
  exception when serialization_failure then null;
  end;

  perform public.research_skill_activate_instructions('coach', draft.version_id, draft.sha256, baseline.version_id);
  if not exists (select 1 from public.research_skill_get_instructions('coach') where version_id = draft.version_id and instructions = content)
    or exists (select 1 from public.research_skill_get_instructions('verifier', draft.version_id))
    or not exists (select 1 from public.research_skill_get_instructions('coach', baseline.version_id) where sha256 = baseline.sha256) then
    raise exception 'Publication broke active, cross-role or pinned reads';
  end if;

  perform public.research_skill_activate_instructions('coach', baseline.version_id, baseline.sha256, draft.version_id);
  if not exists (select 1 from public.research_skill_get_instructions('coach') where version_id = baseline.version_id)
    or not exists (select 1 from public.research_skill_get_instructions('coach', draft.version_id) where instructions = content)
    or (select count(*) from public.research_skill_instruction_publications where role = 'coach') <> 3 then
    raise exception 'Rollback lost an instruction version or audit record';
  end if;
end
$$;

do $$
declare
  client text;
  relation text;
begin
  foreach client in array array['anon', 'authenticated', 'service_role'] loop
    foreach relation in array array['versions', 'settings', 'publications'] loop
      if has_table_privilege(client, 'public.research_skill_instruction_' || relation, 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE') then
        raise exception 'Client can access instruction tables directly';
      end if;
    end loop;
    if has_function_privilege(client, 'public.research_skill_activate_instructions(text,uuid,text,uuid)', 'EXECUTE')
      or has_function_privilege(client, 'public.research_skill_get_instructions(text,uuid)', 'EXECUTE') <> (client = 'service_role') then
      raise exception 'Unexpected client function privileges';
    end if;
  end loop;
end
$$;

set local role service_role;
do $$
begin
  if (select count(*) from public.research_skill_get_instructions('generator')) <> 1 then
    raise exception 'Connector role cannot read the active guidance';
  end if;
end
$$;

rollback;
