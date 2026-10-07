"""Transactional RLS/publication tests; refuses any non-isolated database."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
import bridge
from workflow import canonical

url=os.environ.get('RESEARCH_TEST_DATABASE_URL')
if not url:raise SystemExit('Set RESEARCH_TEST_DATABASE_URL to an isolated jumpserve_research_workflow_test DB')
psql='/opt/homebrew/opt/postgresql@17/bin/psql'
study=str(uuid.UUID('953f20a3-3fd8-4fb4-8844-5d4d72690e01'));actor=str(uuid.UUID('953f20a3-3fd8-4fb4-8844-5d4d72690e02'))
assessment=ROOT.parent/'jumpserve-back-end/experiments/ipv6_dns/evidence/assessment-v2.json'
if not assessment.exists():raise SystemExit('The exact IPv6 assessment is needed for this register import test; no invented replacement.')
package=bridge.ipv6(assessment,study)
def literal(value):return "'"+json.dumps(value,ensure_ascii=False).replace("'","''")+"'::jsonb"

setup="""
begin;
do $$ begin if current_database()<>'jumpserve_research_workflow_test' then raise exception 'Isolated DB required'; end if; end $$;
do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
do $$ begin create role service_role bypassrls; exception when duplicate_object then null; end $$;
grant usage on schema public to anon,authenticated,service_role;
create schema storage;
grant usage on schema storage to anon,authenticated,service_role;
create table storage.buckets(id text primary key,name text,public boolean);
create table storage.objects(id integer primary key,bucket_id text);
alter table storage.objects enable row level security;
grant all on storage.objects to anon,authenticated,service_role;
create policy shared_storage on storage.objects for all to anon,authenticated using(true) with check(true);
insert into storage.objects values(1,'other-bucket'),(2,'research-workflow-raw');
-- Model the production default restrictive anonymous-read policy.
create function public.test_default_restriction() returns event_trigger language plpgsql as $$
declare r record; begin for r in select * from pg_event_trigger_ddl_commands() where command_tag='CREATE TABLE' loop
 if r.object_identity like 'public.research_%' then execute format('create policy jumpserve_require_signed_in_user on %s as restrictive for select to anon using(false)',r.object_identity); end if;
end loop; end $$;
create event trigger test_default_restriction on ddl_command_end when tag in ('CREATE TABLE') execute function public.test_default_restriction();
"""
migration=(ROOT/'database/202610070001_research_workflow.sql').read_text().replace('begin;\n','',1).rsplit('commit;',1)[0]
create=f"select public.research_create_study('{actor}','{study}',{literal(package['paper'])});\n"
append=f"select public.research_append_bundle('{study}','{actor}',{literal(package['records'])});\n"
scientific='953f20a3-3fd8-4fb4-8844-5d4d72690e03';software='953f20a3-3fd8-4fb4-8844-5d4d72690e04';publication='953f20a3-3fd8-4fb4-8844-5d4d72690e05'
reviewer=dict(identity='AI software test fixture',type='AI',independence='Implementer; these synthetic review judgments test publication controls, not an actual scientific review')
reviews=[dict(kind='reviews',record=dict(id=scientific,scope='scientific',status='passed',reviewer=reviewer,judgments=dict(scope_and_limits_reviewed=True),limitations='Isolated SQL fixture; not published to Supabase.')),dict(kind='reviews',record=dict(id=software,scope='software',status='passed',reviewer=reviewer,judgments=dict(release_blockers={k:True for k in ('database','backend','frontend','provenance','access_control')},conditional_verification_gaps=['No real Google session in this isolated DB test']),limitations='Isolated SQL fixture; not a software release report.'))]
append_reviews=f"select public.research_append_bundle('{study}','{actor}',{literal(reviews)});\n"
checks=f"""
set local role anon;
do $$ begin
 if (select count(*) from public.research_studies)<>0 or (select count(*) from public.research_claims)<>0 then raise exception 'Unpublished drafts exposed'; end if;
 if has_table_privilege(current_user,'public.research_claims','INSERT,UPDATE,DELETE') then raise exception 'Browser writes granted'; end if;
 if has_table_privilege(current_user,'public.research_study_owners','SELECT') or has_table_privilege(current_user,'public.research_artifacts','SELECT') then raise exception 'Private metadata exposed'; end if;
 if has_function_privilege(current_user,'public.research_append(uuid,uuid,text,jsonb)','EXECUTE') then raise exception 'Browser RPC writes granted'; end if;
 if (select count(*) from storage.objects)<>1 then raise exception 'Private originals exposed'; end if;
end $$;
reset role;
do $$ begin
 begin perform public.research_append('{study}','953f20a3-3fd8-4fb4-8844-5d4d72690e99','claims','{{}}'); raise exception 'Cross-owner write succeeded'; exception when others then if sqlerrm<>'Study not found' then raise; end if; end;
 begin update public.research_claims set description='overwrite'; raise exception 'Evidence overwrite succeeded'; exception when others then if sqlerrm not like 'Research evidence is append-only%' then raise; end if; end;
 begin perform public.research_publish('{study}','{actor}','{publication}','{scientific}','{software}','fixture'); raise exception 'Missing reviews accepted'; exception when others then if sqlerrm<>'Passed scientific and software reviews required' then raise; end if; end;
end $$;
"""
publish=f"select public.research_publish('{study}','{actor}','{publication}','{scientific}','{software}','Isolated publication fixture');\n"
claim=next(r['record'] for r in package['records'] if r['kind']=='claims')
later=dict(claim,id='953f20a3-3fd8-4fb4-8844-5d4d72690e06',description='Later private draft claim')
late=f"select public.research_append('{study}','{actor}','claims',{literal(later)});\n"
later_gap=dict(next(r['record'] for r in package['records'] if r['kind']=='gaps'),id='953f20a3-3fd8-4fb4-8844-5d4d72690e08',claim_id=later['id'],assessment_id=None)
final=f"""
set local role anon;
do $$ begin
 if (select count(*) from public.research_studies)<>1 then raise exception 'Published study hidden by default restrictive policy'; end if;
 if (select count(*) from public.research_claims)<>15 then raise exception 'Published snapshot changed after new draft'; end if;
 if (select count(*) from public.research_sources)<>74 or (select count(*) from public.research_gaps)<>9 then raise exception 'Register coverage changed'; end if;
end $$;
reset role;
set local role authenticated;
do $$ begin
 if (select count(*) from public.research_claims)<>15 then raise exception 'Browser sees private new drafts'; end if;
 begin insert into public.research_study_owners values('953f20a3-3fd8-4fb4-8844-5d4d72690e06','{actor}'); raise exception 'Owner impersonation succeeded'; exception when insufficient_privilege then null; end;
end $$;
reset role;
do $$ begin
 begin perform public.research_publish('{study}','{actor}','953f20a3-3fd8-4fb4-8844-5d4d72690e07','{scientific}','{software}','Missing gap fixture'); raise exception 'Unresolved claim without gap published'; exception when others then if sqlerrm<>'Every unresolved claim needs a current evidence-gap record' then raise; end if; end;
 if (select count(*) from public.research_claims)<>16 then raise exception 'Private amendment lost'; end if;
end $$;
rollback;
"""
stale_review=f"""
select public.research_append('{study}','{actor}','gaps',{literal(later_gap)});
do $$ begin
 begin perform public.research_publish('{study}','{actor}','953f20a3-3fd8-4fb4-8844-5d4d72690e09','{scientific}','{software}','Stale review fixture'); raise exception 'Stale reviews accepted changed evidence'; exception when others then if sqlerrm<>'Evidence changed after review; new scientific and software reviews required' then raise; end if; end;
end $$;
"""
final=final.replace('rollback;',stale_review+'\nrollback;')
process=subprocess.run([psql,url,'-X','-v','ON_ERROR_STOP=1','-q','-t','-A'],input=setup+migration+create+append+checks+append_reviews+publish+late+final,text=True,capture_output=True)
if process.returncode:
    print(process.stderr,file=sys.stderr);raise SystemExit(process.returncode)
print(json.dumps(dict(passed=True,database='jumpserve_research_workflow_test',rolled_back=True,original_assessment_sha256=package['provenance']['original_sha256'],imported_sources=74,original_claims=15,evidence_gaps=9,checks=['draft privacy','public snapshot','future draft privacy','RLS with default restrictive policy','browser write denial','private storage','RPC authorization','owner isolation','immutable evidence','review gate','unresolved claim gate','stale review rejection']),indent=2))
