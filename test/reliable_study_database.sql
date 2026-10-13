reset role;
insert into reliable_study_protocols(id,version,stage,document,sha256,locked_at) values('test',1,'main','{}',repeat('a',64),now());
insert into reliable_study_campaigns(id,protocol_id,title,stage,status,planned_runs,recorded_runs) values('test','test','Test','main','complete',1,1);
insert into reliable_study_configurations(id,campaign_id,algorithm,skewness,budget_bytes,budget_regime,input_sha256) values('test','test','RS',1,1,'nominal',repeat('a',64));
insert into reliable_study_runs(id,campaign_id,configuration_id,protocol_id,stage,status,algorithm,seed,input_sha256,analysis_sha256,analysis_version) values('test','test','test','test','main','complete','RS',1,repeat('a',64),repeat('a',64),'test');
insert into reliable_study_measurements values('test','zero',0,'recorded',null,'units'),('test','missing',null,'missing','not exposed','units');
insert into reliable_study_artifacts(id,byte_count) values('private',1);
insert into storage.objects values(4,'reliable-study-raw');
set local role anon;
do $$ begin
 if (select count(*) from reliable_study_measurements)<>2 then raise exception 'Public data hidden';end if;
 begin insert into reliable_study_measurements values('test','bad',0,'recorded',null,'units');raise exception 'Anon write permitted';exception when insufficient_privilege then null;end;
 begin perform * from reliable_study_artifacts;raise exception 'Private artifact exposed';exception when insufficient_privilege then null;end;
 if exists(select 1 from storage.objects where bucket_id='reliable-study-raw') then raise exception 'Private raw exposed';end if;
end $$;
reset role;
set local role authenticated;
do $$ begin
 if (select count(*) from reliable_study_measurements)<>2 then raise exception 'Read blocked';end if;
 begin update reliable_study_runs set reason='browser';raise exception 'Browser write permitted';exception when insufficient_privilege then null;end;
end $$;
reset role;
do $$ begin
 begin insert into reliable_study_measurements values('test','bad',0,'missing','absent','units');raise exception 'Missing coerced to zero';exception when check_violation then null;end;
 begin perform publish_agent_prompt('fcb80942-f442-4e52-8d78-7bdf160c5bde',null,'bad','{}','test','reliable-sketch-study');raise exception 'Unevaluated draft published';exception when raise_exception then if sqlerrm='Unevaluated draft published' then raise;end if;end;
 if (select public from storage.buckets where id='reliable-study-raw') then raise exception 'Raw bucket public';end if;
end $$;
