"""Read-only fixed-target HTTP, export and prompt-publication guard checks."""
import ssl,argparse,copy,datetime as dt,hashlib,importlib.util,io,json,urllib.error,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PATH='/module/ipv6-dns-study'
def fetch(url):
 try:
  with urllib.request.urlopen(url,timeout=60,context=ssl.create_default_context(cafile="/etc/ssl/cert.pem")) as r:return r.status,dict(r.headers),r.read(10_000_001),r.url
 except urllib.error.HTTPError as e:return e.code,dict(e.headers),e.read(),e.url
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--production',action='store_true');p.add_argument('--publication-guards',action='store_true');p.add_argument('--report-version',type=int,default=1,choices=range(1,10));a=p.parse_args()
 spec=importlib.util.spec_from_file_location('study_admin',ROOT/'bin/ipv6-study-database.py');admin=importlib.util.module_from_spec(spec);spec.loader.exec_module(admin);targets=admin.targets()
 report=dict(id='ipv6-http-'+('production' if a.production else 'local')+f'-v{a.report_version}',at=dt.datetime.now(dt.timezone.utc).isoformat(),targets=targets,checks=[],passed=False)
 if a.publication_guards:
  evidence=json.loads((ROOT/'docs/ipv6-study-validation/chat-evaluation-v3.json').read_text());pid=evidence['prompt_version_id'];sha=evidence['prompt_content_sha256']
  row=admin.admin.query("select v.id,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id='ipv6-dns-study'")
  assert len(row)==1 and row[0]['id']==pid and row[0]['content_sha256']==sha and row[0]['published_at']
  for name in ('missing-review','missing-names','omitted-case','failed-case'):
   trial=copy.deepcopy(evidence)
   if name=='missing-review':trial.pop('secondary_review')
   elif name=='missing-names':trial['secondary_review'].pop('cases')
   elif name=='omitted-case':trial['secondary_review']['cases']=trial['secondary_review']['cases'][:-1]
   else:trial['cases'][0]['passed']=False
   args=[admin.admin.literal(v) for v in (pid,pid,sha,json.dumps(trial),'ipv6-guard-check','ipv6-dns-study')]
   expected='All required answer evaluations must pass' if name=='failed-case' else 'All IPv6 answer reviews must pass'
   sql='begin; do $guard$ begin perform public.publish_agent_prompt('+','.join(args)+"); raise exception 'Unexpected publication acceptance'; exception when others then if SQLERRM <> "+admin.admin.literal(expected)+" then raise; end if; end $guard$; rollback;"
   admin.admin.query(sql,read_only=False)
   report['checks'].append(dict(name=name,result='rejected transaction; no publication'))
  report['prompt']=row[0]
 else:
  origin='https://jumpserve.quaint-lab.org' if a.production else 'http://127.0.0.1:3000'
  for suffix in ('','/test-results','/methods','/literature'):
   status,headers,raw,url=fetch(origin+PATH+suffix);assert status==200 and b'IPv6' in raw
   report['checks'].append(dict(path=PATH+suffix,status=status,bytes=len(raw)))
  status,_,raw,_=fetch(origin+PATH+'/api/data');assert status==200
  d=json.loads(raw);assert len(d['comparisons'])==1152 and len(d['sources'])==74 and len(d['runs'])==158
  report['checks'].append(dict(path=PATH+'/api/data',status=status,comparisons=1152,sources=74,runs=158,assessment_sha256=d['meta']['assessment_sha256']))
  status,_,raw,_=fetch(origin+PATH+'/download-manifest.json');assert status==200;manifest=json.loads(raw)
  status,_,raw,_=fetch(origin+PATH+'/data.zip');assert status==200 and len(raw)==manifest['data.zip']['bytes'] and hashlib.sha256(raw).hexdigest()==manifest['data.zip']['sha256']
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   members=json.loads(z.read('member-manifest.json'))
   for name,m in members.items():
    data=z.read(name);assert len(data)==m['bytes'] and hashlib.sha256(data).hexdigest()==m['sha256']
  report['checks'].append(dict(path=PATH+'/data.zip',sha256=hashlib.sha256(raw).hexdigest(),members=len(members),all_member_hashes_verified=True))
  status,_,raw,_=fetch(origin+PATH+'/validation-manifest.json');assert status==200;vm=json.loads(raw)['validation.zip']
  status,_,raw,_=fetch(origin+PATH+'/validation.zip');assert status==200 and len(raw)==vm['bytes'] and hashlib.sha256(raw).hexdigest()==vm['sha256']
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   entries=json.loads(z.read('member-manifest.json'))
   for name,m in entries.items():
    content=z.read(name);assert len(content)==m['bytes'] and hashlib.sha256(content).hexdigest()==m['sha256']
  report['checks'].append(dict(path=PATH+'/validation.zip',sha256=hashlib.sha256(raw).hexdigest(),members=len(entries),all_member_hashes_verified=True))
  status,_,raw,_=fetch(origin+PATH+'/api/release');assert status==200 and 'Limited historical' in json.loads(raw)['scientific_status']
  report['checks'].append(dict(path=PATH+'/api/release',status=status,scientific_status=json.loads(raw)['scientific_status']))
  status,_,raw,_=fetch(origin+PATH+'/paper-context.json');assert status==200 and len(json.loads(raw)['figure_coverage'])==21
  report['checks'].append(dict(path=PATH+'/paper-context.json',figures=21,sha256=hashlib.sha256(raw).hexdigest()))
  status,_,raw,url=fetch(origin+PATH+'/chat?configuration=dnssec--mtu1500-v6-only-edns4096');assert status==200 and '/login?next=' in url and 'configuration' in url
  report['checks'].append(dict(path='chat sign-in return',destination=url,authenticated_chat='not exercised: no legitimate Google session'))
  status,_,_,_=fetch(origin+PATH+'/qa-validation');assert status==404
  report['checks'].append(dict(path='temporary invalid-data fixture route',status=404))
 report['passed']=True
 name=f'publication-guards-v{a.report_version}.json' if a.publication_guards else 'http-'+('production' if a.production else 'local')+f'-v{a.report_version}.json'
 dest=ROOT/'docs/ipv6-study-validation'/name
 if dest.exists():raise RuntimeError('Preserve original validation report')
 dest.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
