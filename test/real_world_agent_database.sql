-- The earlier tests leave a published emulated version and one saved emulated session.
do $$ begin
    assert (select count(*) from public.agent_prompt_settings)=2, 'One prompt pointer per module';
    assert (select version from public.get_active_agent_prompt())='v1', 'Legacy default must remain emulated';
    assert not exists(select 1 from public.get_active_agent_prompt('congestion-control-real-world')), 'No fallback to emulated prompt';
    assert (select module_id from public.agent_sessions limit 1)='congestion-control-emulated', 'Existing history backfilled';
end $$;

set local role service_role;
insert into public.agent_prompt_versions(id,version,module_id,system_prompt,research_context,created_by,updated_by)
values('00000000-0000-4000-8000-000000000010','real-world-v1','congestion-control-real-world','Real system','Real science','test','test');
reset role;
create temporary table real_report as select id,content_sha256,jsonb_build_object(
    'prompt_version_id',id,'prompt_version',version,'prompt_content_sha256',content_sha256,
    'module_id',module_id,'model_id','test-model','analysis_version','real-world-chat-v1',
    'cases',(select jsonb_agg(jsonb_build_object('name',name,'passed',true)) from unnest(array[
        'real-world-metrics','real-world-missing-data','real-world-unmatched','real-world-matched',
        'real-world-replication','real-world-bbr-version','real-world-stale','real-world-untrusted-notes']) name)
) report from public.agent_prompt_versions where module_id='congestion-control-real-world';
grant select on real_report to service_role;
set local role service_role;

-- A candidate cannot change another module's active pointer or reuse the wrong evaluation suite.
select pg_temp.expect_failure(format('select public.publish_agent_prompt(%L,%L,%L,%L::jsonb,%L)',
    id,'00000000-0000-4000-8000-000000000001',content_sha256,report,'test'), 'module mismatch') from real_report;
select pg_temp.expect_failure(format('select public.publish_agent_prompt(%L,null,%L,%L::jsonb,%L,%L)',
    id,content_sha256,jsonb_set(report,'{cases,0,passed}','false'),'test','congestion-control-real-world'), 'must pass') from real_report;
select pg_temp.expect_failure(format('select public.publish_agent_prompt(%L,null,%L,%L::jsonb,%L,%L)',
    id,content_sha256,jsonb_set(report,'{module_id}','"congestion-control-emulated"'),'test','congestion-control-real-world'), 'module mismatch') from real_report;
select public.publish_agent_prompt(id,null,content_sha256,report,'test','congestion-control-real-world') from real_report;
select pg_temp.expect_failure($q$update public.agent_prompt_versions set system_prompt='changed' where version='real-world-v1'$q$, 'immutable');
select pg_temp.expect_failure($q$update public.agent_prompt_versions set module_id='congestion-control-emulated' where version='real-world-v1'$q$, 'permission denied');

-- Existing emulated calls still work, and module/owner mismatches cannot overwrite history.
select public.save_agent_turn('00000000-0000-4000-8000-000000000003','test','[]',
    '00000000-0000-4000-8000-000000000006','00000000-0000-4000-8000-000000000001','model','analysis','legacy answer');
select pg_temp.expect_failure($q$select public.save_agent_turn('00000000-0000-4000-8000-000000000003','test','[{}]',
    '00000000-0000-4000-8000-000000000007','00000000-0000-4000-8000-000000000010','model','analysis','wrong module','congestion-control-real-world')$q$, 'owner or module mismatch');
select pg_temp.expect_failure($q$select public.save_agent_turn('00000000-0000-4000-8000-000000000003','intruder','[{}]',
    '00000000-0000-4000-8000-000000000007','00000000-0000-4000-8000-000000000001','model','analysis','wrong owner')$q$, 'owner or module mismatch');
select pg_temp.expect_failure($q$select public.save_agent_turn('00000000-0000-4000-8000-000000000011','test','[]',
    '00000000-0000-4000-8000-000000000012','00000000-0000-4000-8000-000000000001','model','analysis','wrong prompt','congestion-control-real-world')$q$, 'published prompt in the requested module');
select public.save_agent_turn('00000000-0000-4000-8000-000000000011','test','[]',
    '00000000-0000-4000-8000-000000000012','00000000-0000-4000-8000-000000000010','model','real-world-chat-v1','real answer','congestion-control-real-world');
select pg_temp.expect_failure($q$update public.agent_sessions set module_id='congestion-control-emulated'
    where id='00000000-0000-4000-8000-000000000011'$q$, 'module is immutable');
reset role;
do $$ begin
    assert (select version from public.get_active_agent_prompt())='v1', 'Emulated pointer unchanged';
    assert (select version from public.get_active_agent_prompt('congestion-control-real-world'))='real-world-v1', 'Independent real-world pointer';
    assert (select messages from public.agent_sessions where id='00000000-0000-4000-8000-000000000003')='[]'::jsonb, 'Mismatched turn must not modify history';
    assert (select count(*) from public.agent_answers)=3, 'No rejected turn persisted';
end $$;

set local role anon;
select pg_temp.expect_failure($q$select * from public.get_active_agent_prompt('congestion-control-real-world')$q$, 'permission denied');
select pg_temp.expect_failure($q$select public.publish_agent_prompt(null,null,null,null,'intruder','congestion-control-real-world')$q$, 'permission denied');
select pg_temp.expect_failure($q$select public.save_agent_turn(null,'intruder','[]',null,null,'m','a','r','congestion-control-real-world')$q$, 'permission denied');
reset role;
set local role authenticated;
select pg_temp.expect_failure($q$select * from public.get_active_agent_prompt('congestion-control-real-world')$q$, 'permission denied');
select pg_temp.expect_failure($q$select public.publish_agent_prompt(null,null,null,null,'intruder','congestion-control-real-world')$q$, 'permission denied');
reset role;
