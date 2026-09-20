-- Apply once, before deploying the database-backed agent. No existing data changes.
begin;

create table public.agent_prompt_versions (
    id uuid primary key default gen_random_uuid(),
    version text not null unique check (length(btrim(version)) between 1 and 120),
    system_prompt text not null check (length(btrim(system_prompt)) between 1 and 100000),
    research_context text not null check (length(btrim(research_context)) between 1 and 100000),
    content_sha256 text not null,
    created_at timestamptz not null default now(),
    created_by text not null check (btrim(created_by) <> ''),
    updated_at timestamptz not null default now(),
    updated_by text not null check (btrim(updated_by) <> ''),
    published_at timestamptz
);

create table public.agent_prompt_settings (
    singleton boolean primary key default true check (singleton),
    active_version_id uuid references public.agent_prompt_versions(id),
    updated_at timestamptz not null default now()
);
insert into public.agent_prompt_settings (singleton) values (true);

create table public.agent_prompt_publications (
    id uuid primary key default gen_random_uuid(),
    prompt_version_id uuid not null references public.agent_prompt_versions(id),
    previous_version_id uuid references public.agent_prompt_versions(id),
    published_at timestamptz not null default now(),
    published_by text not null,
    evaluation_report jsonb not null
);

create table public.agent_answers (
    id uuid primary key,
    session_id uuid not null references public.agent_sessions(id) on delete cascade,
    prompt_version_id uuid not null references public.agent_prompt_versions(id),
    model_id text not null,
    analysis_version text not null,
    response text not null,
    created_at timestamptz not null default now()
);
create index agent_answers_session_idx on public.agent_answers(session_id, created_at);
create index agent_answers_prompt_idx on public.agent_answers(prompt_version_id);
create index agent_prompt_publications_version_idx on public.agent_prompt_publications(prompt_version_id);
create index agent_prompt_publications_previous_idx on public.agent_prompt_publications(previous_version_id);

alter table public.agent_prompt_versions enable row level security;
alter table public.agent_prompt_settings enable row level security;
alter table public.agent_prompt_publications enable row level security;
alter table public.agent_answers enable row level security;
revoke all on public.agent_prompt_versions, public.agent_prompt_settings,
    public.agent_prompt_publications, public.agent_answers from public, anon, authenticated, service_role;
grant select on public.agent_prompt_versions, public.agent_prompt_settings,
    public.agent_prompt_publications, public.agent_answers to service_role;
grant insert (id, version, system_prompt, research_context, created_by, updated_by)
    on public.agent_prompt_versions to service_role;
grant update (version, system_prompt, research_context, updated_by)
    on public.agent_prompt_versions to service_role;
grant insert on public.agent_answers to service_role;

create function public.protect_agent_prompt_version() returns trigger
language plpgsql set search_path = '' as $$
begin
    if tg_op <> 'INSERT' and old.published_at is not null then
        raise exception 'Published prompt versions are immutable; create a new draft';
    end if;
    if tg_op = 'UPDATE' then
        if new.id <> old.id or new.created_at <> old.created_at or new.created_by <> old.created_by then
            raise exception 'Prompt identity and creation audit are immutable';
        end if;
        new.updated_at = now();
    end if;
    if tg_op = 'DELETE' then return old; end if;
    new.content_sha256 = encode(sha256(convert_to(new.system_prompt || E'\n\n' || new.research_context, 'UTF8')), 'hex');
    return new;
end;
$$;
create trigger protect_agent_prompt_version before insert or update or delete on public.agent_prompt_versions
for each row execute function public.protect_agent_prompt_version();

create function public.get_active_agent_prompt() returns setof public.agent_prompt_versions
language sql stable security invoker set search_path = '' as $$
    select v.* from public.agent_prompt_settings s
    join public.agent_prompt_versions v on v.id = s.active_version_id
    where s.singleton and v.published_at is not null;
$$;

-- Lock the pointer and candidate; never activate content different from the evaluated snapshot.
create function public.publish_agent_prompt(
    p_version_id uuid, p_expected_active_version_id uuid,
    p_expected_content_sha256 text, p_report jsonb, p_actor text
) returns uuid language plpgsql security definer set search_path = '' as $$
declare
    current_id uuid;
    candidate public.agent_prompt_versions;
    required_cases text[] := array['2352', '2352-rephrased', 'correct-prior-error',
        'cubic-control', 'bbr-version-control', 'inconsistent-measurements',
        'unsupported-metrics', 'missing-client-data'];
begin
    select active_version_id into current_id from public.agent_prompt_settings
        where singleton for update;
    if not found then raise exception 'Missing prompt settings'; end if;
    if current_id is distinct from p_expected_active_version_id then
        raise exception 'Active prompt changed during evaluation; review and retry';
    end if;
    select * into strict candidate from public.agent_prompt_versions where id = p_version_id for update;
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
    update public.agent_prompt_settings set active_version_id = p_version_id, updated_at = now() where singleton;
    return p_version_id;
end;
$$;

-- Store history and the answer's exact prompt identity in one transaction.
create function public.save_agent_turn(
    p_session_id uuid, p_user_id text, p_messages jsonb, p_answer_id uuid,
    p_prompt_version_id uuid, p_model_id text, p_analysis_version text, p_response text
) returns uuid language plpgsql security invoker set search_path = '' as $$
begin
    if jsonb_typeof(p_messages) is distinct from 'array' then
        raise exception 'Messages must be an array';
    end if;
    if not exists (select 1 from public.agent_prompt_versions where id = p_prompt_version_id and published_at is not null) then
        raise exception 'Answer must reference a published prompt';
    end if;
    insert into public.agent_sessions (id, user_id, messages, updated_at)
        values (p_session_id, p_user_id, p_messages, now())
        on conflict (id) do update set messages = excluded.messages, user_id = excluded.user_id, updated_at = excluded.updated_at;
    insert into public.agent_answers (id, session_id, prompt_version_id, model_id, analysis_version, response)
        values (p_answer_id, p_session_id, p_prompt_version_id, p_model_id, p_analysis_version, p_response);
    return p_answer_id;
end;
$$;

revoke all on function public.protect_agent_prompt_version(), public.get_active_agent_prompt(),
    public.publish_agent_prompt(uuid, uuid, text, jsonb, text),
    public.save_agent_turn(uuid, text, jsonb, uuid, uuid, text, text, text)
    from public, anon, authenticated;
grant execute on function public.get_active_agent_prompt(),
    public.publish_agent_prompt(uuid, uuid, text, jsonb, text),
    public.save_agent_turn(uuid, text, jsonb, uuid, uuid, text, text, text) to service_role;

comment on table public.agent_prompt_versions is
    'Edit drafts in Supabase. Published versions are immutable. Publish via the Agent Prompt workflow after evaluation.';
comment on table public.agent_prompt_settings is
    'Singleton active prompt pointer. Changed atomically by publish_agent_prompt only.';
notify pgrst, 'reload schema';
commit;
