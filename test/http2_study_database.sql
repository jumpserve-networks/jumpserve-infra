-- Executed only in the isolated transactional prompt test database.
insert into http2_study_protocols(id,version,stage,document,sha256) values('test-http2',1,'test','{}',repeat('a',64));
insert into http2_study_campaigns(id,title,status,protocol,protocol_sha256,artifact_commit,analysis_sha256,planned_runs,recorded_runs,planned_measurements,limitations,provenance,costs)
values('test-http2','test','partial','{}',repeat('a',64),'commit',repeat('b',64),1,1,1,'[]','{}','{}');
set local role anon;
do $$ declare n integer; relation text; begin
 select count(*) into n from http2_study_campaigns;
 if n<>1 then raise exception 'Anonymous HTTP2 public SELECT failed'; end if;
 foreach relation in array array['http2_study_protocols','http2_study_campaigns','http2_study_configurations','http2_study_runs','http2_study_measurements','http2_study_summaries','http2_study_sources','http2_study_claims','http2_study_followups','http2_study_frame_measurements'] loop
  if not has_table_privilege(current_user,relation,'select') then raise exception 'Public result SELECT denied: %',relation; end if;
  if has_table_privilege(current_user,relation,'insert,update,delete') then raise exception 'Browser result mutation granted: %',relation; end if;
 end loop;
 if has_table_privilege(current_user,'http2_study_artifacts','select') then raise exception 'Raw artifact public read granted'; end if;
end $$;

-- The code is unsigned on the wire; above signed-int maximum is valid.
reset role;
insert into http2_study_runs(campaign_id,id,protocol_id,stage,status,analysis_version,units)
values('test-http2','uint32-test','test-http2','test','complete','test','codes');
insert into http2_study_measurements(campaign_id,run_id,test_id,side,description,expected,author_outcome,outcome,status,error_code)
values('test-http2','uint32-test',1,'client','test','error','goaway','goaway','recorded',4294967295);
do $$ begin
 begin
  update http2_study_measurements set error_code=4294967296;
  raise exception 'Overflow accepted';
 exception when check_violation then null; end;
 begin
  update http2_study_measurements set error_code=-1;
  raise exception 'Negative error accepted';
 exception when check_violation then null; end;
end $$;
reset role;
set local role authenticated;
do $$ begin
 if has_table_privilege(current_user,'http2_study_measurements','insert,update,delete') then raise exception 'Authenticated browser mutation granted'; end if;
 if has_table_privilege(current_user,'http2_study_artifacts','select') then raise exception 'Authenticated raw artifact read granted'; end if;
end $$;
reset role;
insert into agent_prompt_versions(id,version,module_id,system_prompt,research_context,created_by,updated_by)
values('4318ec3c-4e79-4c05-904a-100c62772104','http2-test','http2-compliance-study','system','context','test','test');
do $$ declare c public.agent_prompt_versions; r jsonb; begin
 select * into c from agent_prompt_versions where id='4318ec3c-4e79-4c05-904a-100c62772104';
 r=jsonb_build_object('prompt_content_sha256',c.content_sha256,'prompt_version_id',c.id,'prompt_version',c.version,'module_id',c.module_id,'model_id','test','analysis_version','test','cases','[]'::jsonb);
 begin
  perform publish_agent_prompt(c.id,null,c.content_sha256,r,'test',c.module_id);
  raise exception 'Incomplete HTTP2 evaluation accepted';
 exception when others then if sqlerrm not like 'All required answer evaluations must pass%' then raise; end if; end;
 r=r||jsonb_build_object('cases',(select jsonb_agg(jsonb_build_object('name',name,'passed',true)) from unnest(array['http2-units','http2-missing','http2-coverage','http2-uncertainty','http2-discrepancy','http2-untrusted','http2-rejection','http2-scope']) name));
 begin
  perform publish_agent_prompt(c.id,null,c.content_sha256,r,'test',c.module_id);
  raise exception 'Missing human review accepted';
 exception when others then if sqlerrm not like 'Manual HTTP2 answer review must pass%' then raise; end if; end;
 r=r||jsonb_build_object('human_review',jsonb_build_object('passed',true,'reviewer','test','reviewed_case_names',array['http2-units','http2-missing','http2-coverage','http2-uncertainty','http2-discrepancy','http2-untrusted','http2-rejection','http2-scope']));
 perform publish_agent_prompt(c.id,null,c.content_sha256,r,'test',c.module_id);
end $$;

create or replace function auth.uid() returns uuid language sql as $$ select nullif(current_setting('test.auth_uid',true),'')::uuid $$;
create or replace function auth.jwt() returns jsonb language sql as $$ select coalesce(nullif(current_setting('test.auth_jwt',true),''),'{}')::jsonb $$;
insert into agent_sessions(id,user_id,module_id) values('99999999-0000-4000-8000-000000000001','owner@example.test','http2-compliance-study');
insert into agent_answers(id,session_id,prompt_version_id,model_id,analysis_version,response)
values('99999999-0000-4000-8000-000000000002','99999999-0000-4000-8000-000000000001','4318ec3c-4e79-4c05-904a-100c62772104','test','v3','answer');
select set_config('test.auth_uid','99999999-0000-4000-8000-000000000003',true);
select set_config('test.auth_jwt','{"email":"owner@example.test","app_metadata":{"providers":["google"]}}',true);
set local role authenticated;
do $$ begin
 if (select count(*) from get_agent_answer_provenance('99999999-0000-4000-8000-000000000001','http2-compliance-study'))<>1 then raise exception 'Own provenance denied'; end if;
 if (select count(*) from get_agent_answer_provenance('99999999-0000-4000-8000-000000000001','leo-emergency-failover'))<>0 then raise exception 'Cross-module provenance leaked'; end if;
 perform set_config('test.auth_jwt','{"email":"other@example.test","app_metadata":{"providers":["google"]}}',true);
 if (select count(*) from get_agent_answer_provenance('99999999-0000-4000-8000-000000000001','http2-compliance-study'))<>0 then raise exception 'Other user provenance leaked'; end if;
 perform set_config('test.auth_jwt','{"email":"owner@example.test","app_metadata":{"providers":["email"]}}',true);
 if (select count(*) from get_agent_answer_provenance('99999999-0000-4000-8000-000000000001','http2-compliance-study'))<>0 then raise exception 'Non-Google provenance granted'; end if;
end $$;
reset role;
