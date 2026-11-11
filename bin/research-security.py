"""Read-only target and privacy checks shared by current maintenance tools."""
import importlib.util
import json
from pathlib import Path
import ssl
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('research_security_database', ROOT / 'bin/research-workflow-database.py')
db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(db)
admin = db.admin
PRIVATE = ('research_idea_packets', 'research_idea_sessions', 'research_idea_runs', 'research_idea_readiness', 'research_idea_campaign_links')
OPEN = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile='/etc/ssl/cert.pem' if sys.platform=='darwin' else None)))

def target():
 t=db.targets()
 request=urllib.request.Request('https://api.supabase.com/v1/projects/'+admin.PROJECT_REF,headers={'Authorization':'Bearer '+admin.credential()})
 with OPEN.open(request,timeout=20) as response:p=json.load(response)
 if p.get('id')!=admin.PROJECT_REF:raise RuntimeError('Supabase project identity mismatch')
 t['supabase_project_identity_verified']=True
 return t

def verify():
 rows=admin.query("select c.relname,c.relrowsecurity,has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE') anon_access,has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE') browser_access from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relname in ("+','.join(map(admin.literal,PRIVATE))+") order by relname")
 if len(rows)!=5 or any(not r['relrowsecurity'] or r['anon_access'] or r['browser_access'] for r in rows):raise RuntimeError('Idea private relation grants/RLS differ')
 names=['research_save_idea_packet','research_begin_idea_run','research_finish_idea_run','research_accept_idea_plan','research_prepare_idea_campaign','research_idea_ready','research_idea_owner']
 funcs=admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon_execute,has_function_privilege('authenticated',p.oid,'EXECUTE') browser_execute from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public' and proname in ("+','.join(map(admin.literal,names))+") order by proname")
 if len(funcs)!=len(names) or any(r['anon_execute'] or r['browser_execute'] for r in funcs):raise RuntimeError('Browser privileged RPC access or missing functions')
 if admin.query("select count(*) count from research_studies where (study_kind='idea' and paper_url is not null) or (study_kind='paper' and paper_url is null)")[0]['count']!=0:raise RuntimeError('Invalid study origin data')
 bucket=admin.query("select public from storage.buckets where id='research-workflow-raw'")
 if bucket!=[{'public':False}]:raise RuntimeError('Original artifact bucket must remain private')
 return dict(passed=True,security=rows,rpc=funcs,private_originals=bucket,pointers=admin.query('select module_id,active_version_id from agent_prompt_settings order by module_id'))
