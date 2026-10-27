"""User-authorized reset of the frozen 31 paper assessments, never ideas.

Backup original SQL JSON representations and verify them before any write.
Foreign keys/RLS stay enabled. Delete guards are suspended only under table
locks inside one transaction and restored before commit. No Storage deletion.
"""
import argparse,datetime as dt,hashlib,importlib.util,json,pathlib,re,subprocess,uuid
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('paper_reset_admin',ROOT/'bin/agent-prompts.py');admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin)
BASE=ROOT/'.test-artifacts/assessment-reset'
sha=lambda b:hashlib.sha256(b).hexdigest()
stamp=lambda:dt.datetime.now(dt.timezone.utc).isoformat()
def target():
 account=json.loads(subprocess.check_output(['aws','sts','get-caller-identity','--profile','jumpserve'],timeout=20))['Account']
 assert account=='395567831870' and admin.PROJECT_REF=='regphejnlvfpyokpniny'
 assert json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseUrl']=='https://regphejnlvfpyokpniny.supabase.co'
 admin.query('select current_database() database')
 return dict(aws_account=account,supabase_project=admin.PROJECT_REF)
def ident(s):
 if not re.fullmatch('[a-z_]+',s):raise ValueError('Unsafe identifier.')
 return '"'+s+'"'
def condition(table,ids):
 key='id' if table in ('research_studies','research_paper_uploads') else 'study_id'
 return 't.'+ident(key)+' in ('+','.join(admin.literal(str(uuid.UUID(x)))+'::uuid' for x in ids)+')'
def fingerprint(table,predicate,order):
 return "select count(*) n,encode(sha256(convert_to(coalesce(string_agg(encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex'),'' order by "+order+"),''),'UTF8')),'hex') hash from public."+ident(table)+' t where '+predicate
def backup():
 targets=target();studies=admin.query("select id,title,study_kind,created_at from research_studies where study_kind='paper' order by id")
 if len(studies)!=31:raise ValueError('The user authorized the inspected 31 assessments; changed inventory requires explicit scope reconciliation.')
 ids=[s['id'] for s in studies]
 active=admin.query("select (select count(*) from research_autonomy_tasks where study_id in (select id from research_studies where study_kind='paper') and status='running' and lease_until>clock_timestamp())+(select count(*) from research_queue_jobs where study_id in (select id from research_studies where study_kind='paper') and status='running')+(select count(*) from research_model_dispatches where study_id in (select id from research_studies where study_kind='paper') and status='running' and lease_until>clock_timestamp()) n")[0]['n']
 if active:raise ValueError('Drain active paper execution before backing up/deleting.')
 catalog=json.loads((BASE/'catalog-before.json').read_bytes());tables=[t['name'] for t in catalog['tables'] if 'study_id' in t['columns'] or t['name'] in ('research_studies','research_paper_uploads')]
 keys=admin.query("select c.relname table_name,to_jsonb(array_agg(a.attname order by array_position(k.conkey,a.attnum))) cols from pg_constraint k join pg_class c on c.oid=k.conrelid join pg_namespace n on n.oid=c.relnamespace join pg_attribute a on a.attrelid=c.oid and a.attnum=any(k.conkey) where k.contype='p' and n.nspname='public' and c.relname like 'research_%' group by c.relname")
 pk={v['table_name']:v['cols'] for v in keys};graph={t:set() for t in tables}
 for f in catalog['fks']:
  if f['table'] in graph and f['target'] in graph and f['table']!=f['target']:graph[f['table']].add(f['target'])
 done=set();active=set();order=[]
 def visit(t):
  if t in active:raise ValueError('Unexpected FK cycle.')
  if t in done:return
  active.add(t)
  for p in sorted(graph[t]):visit(p)
  active.remove(t);done.add(t);order.append(t)
 for t in sorted(tables):visit(t)
 directory=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(mode=0o700)
 packet=dict(version='paper-assessment-reset-v1',created_at=stamp(),authorization='User explicitly selected all 31 paper assessments including 5 published assessments on 2026-10-25; retain ideas and other modules.',targets=targets,ids=ids,studies=studies,tables={},delete_order=list(reversed(order)),catalog=catalog,raw_storage_objects='Retained in existing private storage; no object deletions.',status='backing-up')
 path=directory/'backup-manifest.json';save=lambda:path.write_text(json.dumps(packet,indent=2)+'\n');save()
 for t in tables:
  predicate=condition(t,ids);sorting=','.join('t.'+ident(k) for k in pk[t]);before=admin.query(fingerprint(t,predicate,sorting))[0];nonpaper=admin.query(fingerprint(t,'not ('+predicate+')',sorting))[0];file=directory/(t+'.jsonl');digest=hashlib.sha256();rows=0
  with file.open('xb') as stream:
   while rows<before['n']:
    limit=25 if t in ('research_autonomy_turns','research_model_dispatches') else 500
    chunk=admin.query('select to_jsonb(t)::text raw from public.'+ident(t)+' t where '+predicate+' order by '+sorting+' offset '+str(rows)+' limit '+str(limit))
    if not chunk:raise ValueError('Incomplete backup page.')
    for record in chunk:
     raw=record['raw'].encode();json.loads(raw);digest.update(sha(raw).encode());stream.write(raw+b'\n');rows+=1
  if rows!=before['n'] or digest.hexdigest()!=before['hash']:raise ValueError('Database changed or backup bytes differ: '+t)
  data=file.read_bytes();assert len(data.splitlines())==rows
  packet['tables'][t]=dict(count=rows,database_hash=before['hash'],nonpaper=nonpaper,primary_key=pk[t],file=file.name,bytes=len(data),sha256=sha(data));save();print(json.dumps(dict(backed_up=t,rows=rows)),flush=True)
 packet['status']='backup-verified';save();(BASE/'selected.txt').write_text(directory.name+'\n');print(json.dumps(dict(directory=str(directory),assessments=31,rows=sum(t['count'] for t in packet['tables'].values()),status=packet['status'])))
def apply(dry_run=False):
 target();directory=BASE/(BASE/'selected.txt').read_text().strip();path=directory/'backup-manifest.json';packet=json.loads(path.read_bytes())
 assert packet['status']=='backup-verified' and len(packet['ids'])==31 and len(set(packet['ids']))==31
 if not dry_run:
  prior=json.loads((directory/'dry-run-receipt.json').read_bytes())
  assert prior['status']=='rolled-back-verified' and prior['backup_manifest_sha256']==sha(path.read_bytes())
 for t,v in packet['tables'].items():
  data=(directory/v['file']).read_bytes();assert sha(data)==v['sha256'] and len(data)==v['bytes']
 sql="begin; set local lock_timeout='5s'; set local statement_timeout='55s'; select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));\n"
 sql+='lock table '+','.join('public.'+ident(t) for t in sorted(packet['tables']))+' in exclusive mode;\n'
 checks=[]
 for t,v in packet['tables'].items():
  sorting=','.join('t.'+ident(k) for k in v['primary_key']);q=fingerprint(t,condition(t,packet['ids']),sorting)
  checks.append("if (select jsonb_build_object('n',n,'hash',hash) from ("+q+")x) <> "+admin.literal(json.dumps(dict(n=v['count'],hash=v['database_hash'])))+"::jsonb then raise exception 'Backup no longer matches "+t+"'; end if;")
 sql+='do $guard$ begin '+''.join(checks)+' end $guard$;\n'
 guards=[x for x in packet['catalog']['triggers'] if x['table'] in packet['tables'] and 'DELETE' in x['definition'] and x['enabled']=='O']
 for g in guards:sql+='alter table public.'+ident(g['table'])+' disable trigger '+ident(g['name'])+';\n'
 for t in packet['delete_order']:sql+='delete from public.'+ident(t)+' t where '+condition(t,packet['ids'])+';\n'
 for g in guards:sql+='alter table public.'+ident(g['table'])+' enable trigger '+ident(g['name'])+';\n'
 checks=[]
 for t,v in packet['tables'].items():
  sorting=','.join('t.'+ident(k) for k in v['primary_key']);q=fingerprint(t,'not ('+condition(t,packet['ids'])+')',sorting)
  checks.append("if (select jsonb_build_object('n',n,'hash',hash) from ("+q+")x) <> "+admin.literal(json.dumps(v['nonpaper']))+"::jsonb then raise exception 'Nonpaper data changed in "+t+"'; end if;")
 checks.append("if exists(select 1 from research_studies where id in ("+','.join(admin.literal(x)+'::uuid' for x in packet['ids'])+")) then raise exception 'Paper rows remain'; end if;")
 sql+='do $guard$ begin '+''.join(checks)+' end $guard$;\n'+('rollback;' if dry_run else 'commit;')
 name='dry-run' if dry_run else 'apply';out=directory/(name+'-receipt.json')
 if out.exists():raise ValueError('Preserve previous reset receipts; inspect before any retry.')
 (directory/(name+'.sql')).write_text(sql)
 result=dict(version=packet['version'],operation=name,started_at=stamp(),sql_sha256=sha(sql.encode()),backup_manifest_sha256=sha(path.read_bytes()),status='running');out.write_text(json.dumps(result,indent=2))
 try:admin.query(sql,read_only=False);result.update(status='rolled-back-verified' if dry_run else 'committed',assessments=31,rows=sum(t['count'] for t in packet['tables'].values()),nonpaper_data_verified_unchanged=True,delete_guards_restored=True,rls_and_foreign_keys_preserved=True)
 except Exception as error:result.update(status='failed-transaction-rolled-back',reason=type(error).__name__);raise
 finally:result['ended_at']=stamp();out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['backup','dry-run','apply']);a=p.parse_args()
 backup() if a.mode=='backup' else apply(a.mode=='dry-run')
