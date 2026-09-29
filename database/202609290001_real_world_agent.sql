-- Run before deploying module-aware chat. Preserve all existing emulated versions/history.
begin;
alter table public.agent_prompt_versions add column module_id text not null default 'congestion-control-emulated'
    check (module_id in ('congestion-control-emulated','congestion-control-real-world'));
alter table public.agent_prompt_versions add constraint agent_prompt_versions_module_identity unique(module_id,id);
grant insert(module_id) on public.agent_prompt_versions to service_role;

alter table public.agent_prompt_settings add column module_id text not null default 'congestion-control-emulated';
alter table public.agent_prompt_settings drop constraint agent_prompt_settings_pkey;
alter table public.agent_prompt_settings add primary key(module_id);
alter table public.agent_prompt_settings add check(module_id in ('congestion-control-emulated','congestion-control-real-world'));
alter table public.agent_prompt_settings add foreign key(module_id,active_version_id)
    references public.agent_prompt_versions(module_id,id);
insert into public.agent_prompt_settings(module_id) values('congestion-control-real-world');

alter table public.agent_sessions add column module_id text not null default 'congestion-control-emulated'
    check(module_id in ('congestion-control-emulated','congestion-control-real-world'));
create index agent_sessions_module_history on public.agent_sessions(user_id,module_id,updated_at desc);
create function public.protect_agent_session_module() returns trigger
language plpgsql set search_path='' as $$
begin
    if new.module_id <> old.module_id then raise exception 'Conversation module is immutable'; end if;
    return new;
end;
$$;
create trigger protect_agent_session_module before update on public.agent_sessions
    for each row execute function public.protect_agent_session_module();
revoke all on function public.protect_agent_session_module() from public,anon,authenticated;

create or replace function public.protect_agent_prompt_version() returns trigger
language plpgsql set search_path = '' as $$
begin
    if tg_op <> 'INSERT' and old.published_at is not null then
        raise exception 'Published prompt versions are immutable; create a new draft';
    end if;
    if tg_op = 'UPDATE' then
        if new.module_id <> old.module_id or new.id <> old.id or new.created_at <> old.created_at or new.created_by <> old.created_by then
            raise exception 'Prompt identity and creation audit are immutable';
        end if;
        new.updated_at = now();
    end if;
    if tg_op = 'DELETE' then return old; end if;
    new.content_sha256 = encode(sha256(convert_to(new.system_prompt || E'\n\n' || new.research_context, 'UTF8')), 'hex');
    return new;
end;
$$;

drop function public.get_active_agent_prompt();
create function public.get_active_agent_prompt(p_module_id text default 'congestion-control-emulated')
returns setof public.agent_prompt_versions language sql stable security invoker set search_path='' as $$
    select v.* from public.agent_prompt_settings s
    join public.agent_prompt_versions v on v.id=s.active_version_id and v.module_id=s.module_id
    where s.module_id=p_module_id and v.published_at is not null;
$$;

drop function public.publish_agent_prompt(uuid,uuid,text,jsonb,text);
create function public.publish_agent_prompt(
    p_version_id uuid, p_expected_active_version_id uuid,
    p_expected_content_sha256 text, p_report jsonb, p_actor text,
    p_module_id text default 'congestion-control-emulated'
) returns uuid language plpgsql security definer set search_path = '' as $$
declare
    current_id uuid;
    candidate public.agent_prompt_versions;
    required_cases text[] := array['2352', '2352-rephrased', 'correct-prior-error',
        'cubic-control', 'bbr-version-control', 'inconsistent-measurements',
        'unsupported-metrics', 'missing-client-data'];
begin
    select active_version_id into current_id from public.agent_prompt_settings
        where module_id=p_module_id for update;
    if not found then raise exception 'Missing prompt settings'; end if;
    if current_id is distinct from p_expected_active_version_id then
        raise exception 'Active prompt changed during evaluation; review and retry';
    end if;
    if p_module_id = 'congestion-control-real-world' then
        required_cases := array['real-world-metrics','real-world-missing-data','real-world-unmatched',
            'real-world-matched','real-world-replication','real-world-bbr-version',
            'real-world-stale','real-world-untrusted-notes'];
    end if;
    select * into strict candidate from public.agent_prompt_versions where id = p_version_id for update;
    if candidate.module_id <> p_module_id then raise exception 'Prompt module mismatch'; end if;
    if p_module_id <> 'congestion-control-emulated' and p_report->>'module_id' is distinct from p_module_id then
        raise exception 'Evaluation module mismatch';
    end if;
    if candidate.content_sha256 is distinct from p_expected_content_sha256
        or p_report->>'prompt_content_sha256' is distinct from candidate.content_sha256
        or p_report->>'prompt_version_id' is distinct from candidate.id::text
        or p_report->>'prompt_version' is distinct from candidate.version then
        raise exception 'Evaluation does not match the candidate prompt';
    end if;
    if coalesce(btrim(p_actor), '') = '' or coalesce(p_report->>'model_id', '') = ''
        or coalesce(p_report->>'analysis_version', '') = '' then
        raise exception 'Publication requires actor, model and analysis metadata';
    end if;
    if jsonb_typeof(p_report->'cases') is distinct from 'array' then
        raise exception 'Missing evaluation cases';
    end if;
    if jsonb_array_length(p_report->'cases') <> cardinality(required_cases)
        or exists (select 1 from unnest(required_cases) name where
            (select count(*) from jsonb_array_elements(p_report->'cases') c
             where c->>'name' = name and c->'passed' = 'true'::jsonb) <> 1) then
        raise exception 'All required answer evaluations must pass';
    end if;
    if candidate.published_at is null then
        update public.agent_prompt_versions set published_at = now(), updated_by = p_actor where id = p_version_id;
    end if;
    insert into public.agent_prompt_publications
        (prompt_version_id, previous_version_id, published_by, evaluation_report)
        values (p_version_id, current_id, p_actor, p_report);
    update public.agent_prompt_settings set active_version_id = p_version_id, updated_at = now() where module_id=p_module_id;
    return p_version_id;
end;
$$;


drop function public.save_agent_turn(uuid,text,jsonb,uuid,uuid,text,text,text);
create function public.save_agent_turn(
    p_session_id uuid, p_user_id text, p_messages jsonb, p_answer_id uuid,
    p_prompt_version_id uuid, p_model_id text, p_analysis_version text, p_response text,
    p_module_id text default 'congestion-control-emulated'
) returns uuid language plpgsql security invoker set search_path='' as $$
declare changed integer;
begin
    if jsonb_typeof(p_messages) is distinct from 'array' then raise exception 'Messages must be an array'; end if;
    if not exists(select 1 from public.agent_prompt_versions
        where id=p_prompt_version_id and published_at is not null and module_id=p_module_id) then
        raise exception 'Answer must reference a published prompt in the requested module';
    end if;
    insert into public.agent_sessions(id,user_id,messages,module_id,updated_at)
        values(p_session_id,p_user_id,p_messages,p_module_id,now())
        on conflict(id) do update set messages=excluded.messages,updated_at=excluded.updated_at
        where agent_sessions.user_id=excluded.user_id and agent_sessions.module_id=excluded.module_id;
    get diagnostics changed=row_count;
    if changed<>1 then raise exception 'Conversation owner or module mismatch'; end if;
    insert into public.agent_answers(id,session_id,prompt_version_id,model_id,analysis_version,response)
        values(p_answer_id,p_session_id,p_prompt_version_id,p_model_id,p_analysis_version,p_response);
    return p_answer_id;
end;
$$;

revoke all on function public.get_active_agent_prompt(text),public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),
    public.save_agent_turn(uuid,text,jsonb,uuid,uuid,text,text,text,text) from public,anon,authenticated;
grant execute on function public.get_active_agent_prompt(text),public.publish_agent_prompt(uuid,uuid,text,jsonb,text,text),
    public.save_agent_turn(uuid,text,jsonb,uuid,uuid,text,text,text,text) to service_role;
comment on table public.agent_prompt_settings is 'One evaluated active prompt per module; publish_agent_prompt changes each pointer atomically.';
notify pgrst,'reload schema';
commit;
