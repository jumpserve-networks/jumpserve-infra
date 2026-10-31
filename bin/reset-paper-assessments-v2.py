"""Reset the currently frozen paper assessments under explicit user instruction.

Fixed JumpServe targets; preserve ideas, other modules, prompt publications,
profiles, original private Storage and every earlier reset backup/receipt.
"""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import io
import urllib.error
import urllib.request
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reset_release',ROOT/'bin/openclaw-release.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/assessment-reset-v2'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
stamp=lambda:dt.datetime.now(dt.timezone.utc).isoformat()
def ident(name):
    if not re.fullmatch(r'[a-z_][a-z0-9_]*',name):raise ValueError('Unsafe schema identifier.')
    return '"'+name+'"'
def predicate(table,ids):
    if not ids:return 'false'
    key='id' if table in ('research_studies','research_paper_uploads') else 'study_id'
    return 't.'+ident(key)+' in ('+','.join(r.admin.literal(str(uuid.UUID(x)))+'::uuid' for x in ids)+')'
def catalog():
    return dict(tables=r.admin.query("""select c.relname name,c.relrowsecurity rls,
      (select jsonb_agg(a.attname order by a.attnum) from pg_attribute a where a.attrelid=c.oid and a.attnum>0 and not a.attisdropped) columns,
      (select jsonb_agg(a.attname order by array_position(k.conkey,a.attnum)) from pg_constraint k join pg_attribute a on a.attrelid=c.oid and a.attnum=any(k.conkey) where k.conrelid=c.oid and k.contype='p') primary_key
      from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and c.relname like 'research_%' order by c.relname"""),
      fks=r.admin.query("""select child.relname child,parent.relname parent,k.conname name,pg_get_constraintdef(k.oid) definition
        from pg_constraint k join pg_class child on child.oid=k.conrelid join pg_class parent on parent.oid=k.confrelid
        join pg_namespace n on n.oid=child.relnamespace join pg_namespace p on p.oid=parent.relnamespace
        where k.contype='f' and n.nspname='public' and p.nspname='public' and (child.relname like 'research_%' or parent.relname like 'research_%') order by child.relname,k.conname"""),
      triggers=r.admin.query("""select c.relname table_name,t.tgname name,t.tgenabled enabled,pg_get_triggerdef(t.oid) definition
        from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace
        where not t.tgisinternal and n.nspname='public' and c.relname like 'research_%' order by c.relname,t.tgname"""))
def inspect():
    targets=r.target();data=catalog()
    studies=r.admin.query("select s.id,s.title,s.study_kind,s.created_at,exists(select 1 from research_publications p where p.study_id=s.id) published from research_studies s where s.study_kind='paper' order by s.id")
    ids=[x['id'] for x in studies]
    scoped=[x for x in data['tables'] if 'study_id' in x['columns'] or x['name'] in ('research_studies','research_paper_uploads')]
    counts=r.admin.query(' union all '.join('select '+r.admin.literal(x['name'])+' table_name,count(*) n from public.'+ident(x['name'])+' t where '+predicate(x['name'],ids) for x in scoped))
    states={}
    for name in ('research_autonomy_tasks','research_model_dispatches','research_queue_jobs','research_network_executions'):
        table=next(x for x in scoped if x['name']==name)
        key=next(x for x in ('status','phase') if x in table['columns'])
        states[name]=r.admin.query('select '+ident(key)+' state,count(*) n from public.'+ident(name)+' t where '+predicate(name,ids)+' group by '+ident(key))
    out=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True,mode=0o700)
    record=dict(version='paper-assessment-reset-v2',authorization='Current user explicitly requests removing all paper assessments from the database, including published papers and linked records.',created_at=stamp(),targets=targets,studies=studies,ids=ids,ids_sha256=sha(json.dumps(sorted(ids),separators=(',',':')).encode()),catalog=data,counts=counts,states=states,nonpaper_studies=r.admin.query("select study_kind,count(*) n from research_studies where study_kind<>'paper' group by study_kind"),scope='Paper assessment database records only. No Storage/object deletion, profiles, research ideas, other module tables or global prompt/evaluation deletion.')
    (out/'inventory.json').write_text(json.dumps(record,indent=2)+'\n');(BASE/'selected.txt').write_text(out.name+'\n')
    print(json.dumps(dict(directory=str(out),targets=targets,paper_assessments=len(ids),published=sum(x['published'] for x in studies),linked_rows=sum(x['n'] for x in counts),counts=counts,states=states,nonpaper_studies=record['nonpaper_studies']),indent=2))
def selected():
    name=(BASE/'selected.txt').read_text().strip();assert name.isalnum()
    out=BASE/name;data=json.loads((out/'inventory.json').read_bytes())
    assert data['ids_sha256']==sha(json.dumps(sorted(data['ids']),separators=(',',':')).encode())
    return out,data
def fingerprint(table,pred):
    order=','.join('t.'+ident(k) for k in table['primary_key']);assert order
    return "select count(*) n,encode(sha256(convert_to(coalesce(string_agg(encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex'),'' order by "+order+"),''),'UTF8')),'hex') hash from public."+ident(table['name'])+' t where '+pred
def no_active(ids):
    sql="select (select count(*) from research_autonomy_tasks t where "+predicate('research_autonomy_tasks',ids)+" and status in ('queued','running','waiting'))+(select count(*) from research_queue_jobs t where "+predicate('research_queue_jobs',ids)+" and status in ('queued','running'))+(select count(*) from research_model_dispatches t where "+predicate('research_model_dispatches',ids)+" and (status in ('queued','running') or (status='unknown' and greatest(created_at,coalesce(lease_until,created_at),coalesce(ended_at,created_at))>clock_timestamp()-interval '10 minutes')))+(select count(*) from research_network_executions t where "+predicate('research_network_executions',ids)+" and phase not in ('completed','failed','cancelled')) n"
    assert r.admin.query(sql)[0]['n']==0,'Drain/cancel active paper work before reset; do not delete live execution records.'
def backup():
    r.target();out,data=selected();assert data['ids'],'No papers to delete.'
    ids=data['ids'];assert [x['id'] for x in r.admin.query("select id from research_studies where study_kind='paper' order by id")]==ids
    assert catalog()==data['catalog'],'Schema changed since inspection.'
    no_active(ids);path=out/'backup-manifest.json';assert not path.exists(),'Preserve the existing backup; do not silently restart it.'
    tables=[x for x in data['catalog']['tables'] if 'study_id' in x['columns'] or x['name'] in ('research_studies','research_paper_uploads')]
    queries=[]
    for t in tables:
        pred=predicate(t['name'],ids)
        queries.append('select '+r.admin.literal(t['name'])+' table_name,(select to_jsonb(x) from ('+fingerprint(t,pred)+')x) target,(select to_jsonb(x) from ('+fingerprint(t,'not (('+pred+') is true)')+')x) preserved')
    snapshots={x['table_name']:x for x in r.admin.query(' union all '.join(queries))}
    packet=dict(version='paper-assessment-reset-v2',created_at=stamp(),ids=ids,ids_sha256=data['ids_sha256'],tables={},status='backing-up',raw_storage='Retained; no object deletion.')
    def save():path.write_text(json.dumps(packet,indent=2)+'\n');path.chmod(0o600)
    save()
    for t in tables:
        name=t['name'];pred=predicate(name,ids);before=snapshots[name];file=out/(name+'.jsonl');rows=0;digest=hashlib.sha256()
        with file.open('xb') as stream:
            file.chmod(0o600)
            while rows<before['target']['n']:
                size=10 if name in ('research_autonomy_turns','research_model_dispatches') else 25 if name=='research_paper_review_events' else 500
                order=','.join('t.'+ident(k) for k in t['primary_key'])
                chunk=r.admin.query('select to_jsonb(t)::text raw from public.'+ident(name)+' t where '+pred+' order by '+order+' offset '+str(rows)+' limit '+str(size));assert chunk,'Incomplete backup page.'
                for row in chunk:
                    raw=row['raw'].encode();json.loads(raw);stream.write(raw+b'\n');digest.update(sha(raw).encode());rows+=1
        assert rows==before['target']['n'] and digest.hexdigest()==before['target']['hash'],'Backup changed: '+name
        raw=file.read_bytes();packet['tables'][name]=dict(table=t,target=before['target'],preserved=before['preserved'],file=file.name,bytes=len(raw),sha256=sha(raw));save()
        if rows:print(json.dumps(dict(backed_up=name,rows=rows,bytes=len(raw))),flush=True)
    packet['status']='backup-verified';save();print(json.dumps(dict(status=packet['status'],papers=len(ids),rows=sum(x['target']['n'] for x in packet['tables'].values()),bytes=sum(x['bytes'] for x in packet['tables'].values()))))
def archive():
    r.target();out,data=selected();packet=json.loads((out/'backup-manifest.json').read_bytes());assert packet['status']=='backup-verified'
    assert r.admin.query("select public from storage.buckets where id='research-workflow-raw'")==[dict(public=False)]
    files={name:(out/name).read_bytes() for name in ('inventory.json','backup-manifest.json')}
    for item in packet['tables'].values():
        raw=(out/item['file']).read_bytes();assert sha(raw)==item['sha256'];files[item['file']]=raw
    files['reset-producer.py']=Path(__file__).read_bytes()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(files.items()):z.writestr(name,raw)
        z.writestr('artifact-manifest.json',json.dumps([dict(path=n,bytes=len(b),sha256=sha(b)) for n,b in sorted(files.items())]))
    raw=stream.getvalue();assert len(raw)<=32000000
    key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];headers={'apikey':key,'Authorization':'Bearer '+key}
    object_path='administrative-backups/paper-assessment-reset-v2/'+out.name+'/'+sha(raw)+'.zip';url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+object_path
    try:
        with r.prior.guard.OPEN.open(urllib.request.Request(url,data=raw,headers={**headers,'Content-Type':'application/zip'},method='POST'),timeout=60) as response:response.read(1000)
    except urllib.error.HTTPError as error:
        if error.code!=409:raise
    with r.prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=60) as response:restored=response.read(32000001)
    assert restored==raw
    with zipfile.ZipFile(io.BytesIO(restored)) as z:
        for entry in json.loads(z.read('artifact-manifest.json')):assert sha(z.read(entry['path']))==entry['sha256']
    public_key=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'];status=200
    try:
        with r.prior.guard.OPEN.open(urllib.request.Request(url,headers={'apikey':public_key,'Authorization':'Bearer '+public_key}),timeout=20) as response:response.read(1)
    except urllib.error.HTTPError as error:status=error.code
    assert status in (400,401,403,404),'Backup must not be anonymous-readable.'
    (out/'backup.zip').write_bytes(raw);receipt=dict(path=object_path,sha256=sha(raw),retrieved_sha256=sha(restored),bytes=len(raw),members=len(files),private=True,anonymous_read_status=status,backup_manifest_sha256=sha((out/'backup-manifest.json').read_bytes()))
    (out/'backup-archive.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
def apply(dry_run):
    r.target();out,data=selected();path=out/'backup-manifest.json';packet=json.loads(path.read_bytes());assert packet['status']=='backup-verified'
    archive=json.loads((out/'backup-archive.json').read_bytes());assert archive['sha256']==archive['retrieved_sha256'] and archive['backup_manifest_sha256']==sha(path.read_bytes())
    # Exercise a valid anonymous-role request, not merely a missing auth header.
    public_key=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'];public_status=200
    request=urllib.request.Request('https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+archive['path'],headers={'apikey':public_key,'Authorization':'Bearer '+public_key})
    try:
        with r.prior.guard.OPEN.open(request,timeout=20) as response:response.read(1)
    except urllib.error.HTTPError as error:public_status=error.code
    assert public_status in (400,401,403,404),'Original backup is accessible to the anonymous role.'
    (out/'backup-access-verification.json').write_text(json.dumps(dict(role='anon',authorization_header_present=True,status=public_status,verified_at=stamp()),indent=2)+'\n')
    assert catalog()==data['catalog'],'Schema changed after backup.'
    no_active(data['ids'])
    for item in packet['tables'].values():assert sha((out/item['file']).read_bytes())==item['sha256']
    if not dry_run:
        prior=json.loads((out/'dry-run-receipt.json').read_bytes());assert prior['status']=='rolled-back-verified' and prior['backup_manifest_sha256']==sha(path.read_bytes())
    active={n for n,v in packet['tables'].items() if v['target']['n']};graph={n:set() for n in active};order=[];done=set();visiting=set()
    for fk in data['catalog']['fks']:
        if fk['child'] in active and fk['parent'] in active and fk['child']!=fk['parent']:graph[fk['child']].add(fk['parent'])
    def visit(name):
        assert name not in visiting,'Unexpected foreign-key cycle.'
        if name in done:return
        visiting.add(name)
        for parent in sorted(graph[name]):visit(parent)
        visiting.remove(name);done.add(name);order.append(name)
    for name in sorted(graph):visit(name)
    sql="begin; set local lock_timeout='5s'; set local statement_timeout='55s'; select pg_advisory_xact_lock(hashtextextended('research-autonomy-v1',0));\n"
    sql+='lock table '+','.join('public.'+ident(n) for n in sorted(packet['tables']))+' in exclusive mode;\n'
    guards=[x for x in data['catalog']['triggers'] if x['table_name'] in active and 'DELETE' in x['definition'] and x['enabled']!='D']
    checks=["if (select coalesce(jsonb_agg(id order by id),'[]'::jsonb) from public.research_studies where study_kind='paper') <> "+r.admin.literal(json.dumps(data['ids']))+"::jsonb then raise exception 'Paper inventory changed'; end if;"]
    for name,v in packet['tables'].items():
        for pred,expected in ((predicate(name,data['ids']),v['target']),('not (('+predicate(name,data['ids'])+') is true)',v['preserved'])):
            checks.append('if (select to_jsonb(x) from ('+fingerprint(v['table'],pred)+')x) <> '+r.admin.literal(json.dumps(expected))+"::jsonb then raise exception 'Backup changed: "+name+"'; end if;")
    sql+='do $guard$ begin '+''.join(checks)+' end $guard$;\n'
    for trigger in guards:sql+='alter table public.'+ident(trigger['table_name'])+' disable trigger '+ident(trigger['name'])+';\n'
    for name in reversed(order):sql+='delete from public.'+ident(name)+' t where '+predicate(name,data['ids'])+';\n'
    for trigger in guards:
        mode={'O':'enable','A':'enable always','R':'enable replica'}[trigger['enabled']]
        sql+='alter table public.'+ident(trigger['table_name'])+' '+mode+' trigger '+ident(trigger['name'])+';\n'
    checks=[]
    for name,v in packet['tables'].items():
        pred=predicate(name,data['ids']);checks.append('if exists(select 1 from public.'+ident(name)+' t where '+pred+") then raise exception 'Target records remain: "+name+"'; end if;")
        checks.append('if (select to_jsonb(x) from ('+fingerprint(v['table'],'not (('+pred+') is true)')+')x) <> '+r.admin.literal(json.dumps(v['preserved']))+"::jsonb then raise exception 'Preserved records changed: "+name+"'; end if;")
    sql+='do $guard$ begin '+''.join(checks)+' end $guard$;\n'+('rollback;' if dry_run else 'commit;')
    name='dry-run' if dry_run else 'apply';receipt=out/(name+'-receipt.json');assert not receipt.exists(),'Preserve original receipts; inspect before retry.'
    (out/(name+'.sql')).write_text(sql)
    result=dict(operation=name,status='running',started_at=stamp(),sql_sha256=sha(sql.encode()),backup_manifest_sha256=sha(path.read_bytes()))
    try:
        r.admin.query(sql,read_only=False);result.update(status='rolled-back-verified' if dry_run else 'committed',paper_assessments=len(data['ids']),deleted_rows=sum(x['target']['n'] for x in packet['tables'].values()),nonpaper_fingerprints_unchanged=True,foreign_keys_and_RLS_preserved=True,delete_guards_restored=True)
    except Exception as error:result.update(status='failed',reason=str(error));raise
    finally:result['ended_at']=stamp();receipt.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
def verify():
    r.target();out,data=selected();packet=json.loads((out/'backup-manifest.json').read_bytes());assert json.loads((out/'apply-receipt.json').read_bytes())['status']=='committed'
    assert catalog()==data['catalog'],'RLS, columns, constraints or trigger definitions/states changed.'
    assert r.admin.query("select count(*) n from research_studies where study_kind='paper'")==[dict(n=0)]
    queries=['select '+r.admin.literal(name)+' name,(select to_jsonb(x) from ('+fingerprint(v['table'],'not (('+predicate(name,data['ids'])+') is true)')+')x) fingerprint from (select 1)z' for name,v in packet['tables'].items()]
    for row in r.admin.query(' union all '.join(queries)):assert row['fingerprint']==packet['tables'][row['name']]['preserved'],row['name']
    with r.prior.guard.OPEN.open('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/papers',timeout=30) as response:raw=response.read(1000000)
    public=json.loads(raw);assert public['papers']==[] and public['coverage']['papers']==0 and public['next_cursor'] is None
    (out/'public-paper-catalog.json').write_bytes(raw)
    result=dict(status='verified',verified_at=stamp(),paper_assessments_remaining=0,paper_assessments_deleted=len(data['ids']),rows_deleted=sum(x['target']['n'] for x in packet['tables'].values()),nonpaper_studies=data['nonpaper_studies'],all_scoped_nonpaper_fingerprints_unchanged=True,all_schema_and_trigger_states_unchanged=True,private_raw_storage_retained=True,backup_manifest_sha256=sha((out/'backup-manifest.json').read_bytes()))
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['inspect','backup','archive','dry-run','apply','verify']);args=parser.parse_args()
    if args.mode=='inspect':inspect()
    elif args.mode=='backup':backup()
    elif args.mode=='archive':archive()
    elif args.mode=='verify':verify()
    else:apply(args.mode=='dry-run')
if __name__=='__main__':main()
