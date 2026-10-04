begin;
create or replace function public.publish_agent_prompt(
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
    if p_module_id = 'leo-emergency-failover' then
        required_cases := array['leo-units','leo-discrepancy','leo-replication','leo-missing','leo-cable-proxy','leo-coverage','leo-untrusted','leo-placement'];
    end if;
    if p_module_id = 'http2-compliance-study' then
        required_cases := array['http2-units','http2-missing','http2-coverage','http2-uncertainty','http2-discrepancy','http2-untrusted','http2-rejection','http2-scope'];
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



commit;
