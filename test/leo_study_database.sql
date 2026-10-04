insert into public.leo_study_campaigns(id,title,status,protocol,protocol_sha256,artifact_commit,paper_sha256,planned_samples,recorded_samples,limitations,provenance)
values('test-leo','test','complete','{}',repeat('a',64),'commit','hash',1,1,'[]','{}');
set local role anon;
do $$ declare n integer; begin
  select count(*) into n from public.leo_study_campaigns;
  if n<>1 then raise exception 'Anonymous public study SELECT failed'; end if;
  if has_table_privilege(current_user,'public.leo_study_samples','insert') then raise exception 'Anonymous sample INSERT granted'; end if;
  if has_table_privilege(current_user,'public.leo_study_samples','update') then raise exception 'Anonymous sample UPDATE granted'; end if;
  if has_table_privilege(current_user,'public.agent_prompt_versions','select') then raise exception 'Anonymous prompt access granted'; end if;
end $$;
reset role;
set local role authenticated;
do $$ begin
  if has_table_privilege(current_user,'public.leo_study_samples','insert') then raise exception 'Browser sample INSERT granted'; end if;
  if has_table_privilege(current_user,'public.leo_study_campaigns','delete') then raise exception 'Browser campaign DELETE granted'; end if;
end $$;
reset role;
insert into public.agent_prompt_versions(id,version,module_id,system_prompt,research_context,created_by,updated_by)
values('ec00a4b6-718c-4e69-9c0f-283b9f251002','test-leo','leo-emergency-failover','system','context','test','test');
do $$ declare candidate public.agent_prompt_versions; report jsonb; begin
  select * into candidate from public.agent_prompt_versions where id='ec00a4b6-718c-4e69-9c0f-283b9f251002';
  report=jsonb_build_object('prompt_content_sha256',candidate.content_sha256,'prompt_version_id',candidate.id,'prompt_version',candidate.version,'module_id','leo-emergency-failover','model_id','test','analysis_version','test','cases','[]'::jsonb);
  begin
    perform public.publish_agent_prompt(candidate.id,null,candidate.content_sha256,report,'test','leo-emergency-failover');
    raise exception 'Missing LEO cases accepted';
  exception when others then
    if sqlerrm not like 'All required answer evaluations must pass%' then raise; end if;
  end;
  report=report || jsonb_build_object('cases',(select jsonb_agg(jsonb_build_object('name',name,'passed',true)) from unnest(array['leo-units','leo-discrepancy','leo-replication','leo-missing','leo-cable-proxy','leo-coverage','leo-untrusted','leo-placement']) name));
  perform public.publish_agent_prompt(candidate.id,null,candidate.content_sha256,report,'test','leo-emergency-failover');
  if (select active_version_id from public.agent_prompt_settings where module_id='leo-emergency-failover')<>candidate.id then raise exception 'LEO prompt publication failed'; end if;
end $$;
