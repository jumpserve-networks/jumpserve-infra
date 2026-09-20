create function pg_temp.expect_failure(statement text, pattern text) returns void language plpgsql as $$
begin
    begin
        execute statement;
    exception when others then
        if sqlerrm ~ pattern then return; end if;
        raise;
    end;
    raise exception 'Expected operation to fail: %', statement;
end;
$$;

set local role service_role;
insert into public.agent_prompt_versions (id, version, system_prompt, research_context, created_by, updated_by)
values ('00000000-0000-4000-8000-000000000001', 'v1', 'Prompt α', 'Context β', 'test', 'test'),
       ('00000000-0000-4000-8000-000000000002', 'v2', 'Second prompt', 'Second context', 'test', 'test');
select pg_temp.expect_failure($q$update public.agent_prompt_settings set active_version_id='00000000-0000-4000-8000-000000000001'$q$, 'permission denied');
select pg_temp.expect_failure($q$update public.agent_prompt_versions set published_at=now()$q$, 'permission denied');
reset role;

create temporary table reports as
select id, content_sha256, jsonb_build_object(
    'prompt_version_id', id, 'prompt_version', version, 'prompt_content_sha256', content_sha256,
    'model_id', 'test-model', 'analysis_version', 'test-analysis',
    'cases', (select jsonb_agg(jsonb_build_object('name', name, 'passed', true)) from unnest(array[
        '2352','2352-rephrased','correct-prior-error','cubic-control','bbr-version-control',
        'inconsistent-measurements','unsupported-metrics','missing-client-data']) name)
) report from public.agent_prompt_versions;
grant select on reports to service_role;
set local role service_role;

-- Failed/incomplete evaluations and wrong hashes cannot activate even the first version.
select pg_temp.expect_failure(format('select public.publish_agent_prompt(%L,null,%L,%L::jsonb,%L)',
    id, content_sha256, jsonb_set(report, '{cases,0,passed}', 'false'), 'test'), 'must pass') from reports limit 1;
select pg_temp.expect_failure(format('select public.publish_agent_prompt(%L,null,%L,%L::jsonb,%L)',
    id, 'wrong', report, 'test'), 'does not match') from reports limit 1;
select pg_temp.expect_failure(format('select public.publish_agent_prompt(%L,null,%L,%L::jsonb,%L)',
    id, content_sha256, jsonb_set(report, '{cases}', '[]'), 'test'), 'must pass') from reports limit 1;

select public.publish_agent_prompt(id, null, content_sha256, report, 'test') from reports
where id='00000000-0000-4000-8000-000000000001';
select pg_temp.expect_failure($q$update public.agent_prompt_versions set research_context='changed',updated_by='test' where version='v1'$q$, 'immutable');

-- Publishing while an evaluation was running invalidates the old expected pointer.
select pg_temp.expect_failure(format('select public.publish_agent_prompt(%L,null,%L,%L::jsonb,%L)',
    id, content_sha256, report, 'test'), 'changed during evaluation') from reports where id='00000000-0000-4000-8000-000000000002';
update public.agent_prompt_versions set system_prompt='edited draft',updated_by='editor' where version='v2';
select pg_temp.expect_failure(format('select public.publish_agent_prompt(%L,%L,%L,%L::jsonb,%L)',
    id, '00000000-0000-4000-8000-000000000001', content_sha256, report, 'test'), 'does not match')
from reports where id='00000000-0000-4000-8000-000000000002';
update public.agent_prompt_versions set system_prompt='Second prompt',updated_by='editor' where version='v2';
select public.publish_agent_prompt(id, '00000000-0000-4000-8000-000000000001', content_sha256, report, 'test')
from reports where id='00000000-0000-4000-8000-000000000002';
-- Rollback uses a previous immutable version and records a new publication.
select public.publish_agent_prompt(id, '00000000-0000-4000-8000-000000000002', content_sha256, report, 'rollback-test')
from reports where id='00000000-0000-4000-8000-000000000001';

select public.save_agent_turn('00000000-0000-4000-8000-000000000003', 'test', '[]',
    '00000000-0000-4000-8000-000000000004', '00000000-0000-4000-8000-000000000001', 'test-model', 'test-analysis', 'answer');
-- A late insert failure must also roll back the session update.
select pg_temp.expect_failure($q$select public.save_agent_turn('00000000-0000-4000-8000-000000000003', 'changed', '[{}]',
    '00000000-0000-4000-8000-000000000005', '00000000-0000-4000-8000-000000000001', null, 'test-analysis', 'answer')$q$, 'null value');
reset role;

do $$ begin
    if (select count(*) from public.get_active_agent_prompt()) <> 1 then raise exception 'Active prompt missing'; end if;
    if (select version from public.get_active_agent_prompt()) <> 'v1' then raise exception 'Rollback failed'; end if;
    if (select count(*) from public.agent_prompt_publications) <> 3 then raise exception 'Missing publication audit'; end if;
    if (select count(*) from public.agent_answers) <> 1 then raise exception 'Missing answer audit'; end if;
    if (select user_id from public.agent_sessions limit 1) <> 'test' then raise exception 'Session write was not atomic'; end if;
    if exists (select 1 from pg_class where oid in ('public.agent_prompt_versions'::regclass,
        'public.agent_prompt_settings'::regclass,'public.agent_prompt_publications'::regclass,'public.agent_answers'::regclass)
        and not relrowsecurity) then raise exception 'RLS not enabled'; end if;
end $$;
set local role anon;
select pg_temp.expect_failure('select * from public.agent_prompt_versions', 'permission denied');
select pg_temp.expect_failure('select * from public.get_active_agent_prompt()', 'permission denied');
select pg_temp.expect_failure($q$select public.publish_agent_prompt(null,null,null,null,'intruder')$q$, 'permission denied');
select pg_temp.expect_failure('select * from public.agent_answers', 'permission denied');
reset role;
set local role authenticated;
select pg_temp.expect_failure('select * from public.agent_prompt_versions', 'permission denied');
select pg_temp.expect_failure($q$select public.publish_agent_prompt(null,null,null,null,'intruder')$q$, 'permission denied');
reset role;
