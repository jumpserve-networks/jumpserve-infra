"""Read-only verification of the explicitly authorized paper-assessment reset."""
import datetime as dt,hashlib,importlib.util,json,pathlib,ssl,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('reset_verification_admin',ROOT/'bin/agent-prompts.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
base=ROOT/'.test-artifacts/assessment-reset';directory=base/(base/'selected.txt').read_text().strip();packet=json.loads((directory/'backup-manifest.json').read_bytes());before=packet['catalog']
tables=a.query("select c.relname,c.relrowsecurity from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and c.relname like 'research_%'")
triggers=a.query("select tgrelid::regclass::text table_name,tgname name,tgenabled enabled,pg_get_triggerdef(oid) definition from pg_trigger where not tgisinternal and tgrelid::regclass::text like 'research_%'")
assert all({x['relname']:x['relrowsecurity'] for x in tables}[x['name']]==x['rls'] for x in before['tables'])
assert {(x['table'],x['name']):(x['enabled'],x['definition']) for x in before['triggers']}=={(x['table_name'],x['name']):(x['enabled'],x['definition']) for x in triggers}
assert a.query("select study_kind,count(*) n from research_studies group by study_kind")==[dict(study_kind='idea',n=4)]
with urllib.request.urlopen('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/papers',timeout=30,context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')) as response:public=json.load(response)
assert public['papers']==[] and public['coverage']['papers']==0 and public['next_cursor'] is None
report=dict(version='paper-assessment-reset-verification-v1',verified_at=dt.datetime.now(dt.timezone.utc).isoformat(),paper_assessments_remaining=0,research_ideas_remaining=4,previous_assessments_public_count=0,rls_unchanged=True,all_trigger_definitions_and_enabled_states_unchanged=True,backup_manifest_sha256=hashlib.sha256((directory/'backup-manifest.json').read_bytes()).hexdigest(),backup_bytes=sum(x['bytes'] for x in packet['tables'].values()),deleted_rows=60310,retained_raw_files='Existing private storage objects retained; no Storage deletions requested or performed.')
(directory/'verification.json').write_text(json.dumps(report,indent=2)+'\n');(directory/'reset-producer.py').write_bytes((ROOT/'bin/reset-paper-assessments.py').read_bytes());print(json.dumps(dict(directory=str(directory),**report),indent=2))
