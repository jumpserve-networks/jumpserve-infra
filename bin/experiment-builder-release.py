"""Fixed-target builder release prerequisites; no arbitrary shell/SQL arguments."""
import argparse,base64,datetime as dt,hashlib,importlib.util,io,json,pathlib,shlex,subprocess,urllib.request,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('builder_prior_release',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/experiment-builder-release'
MIGRATIONS=[
 ('202610260001_executable_assessment_methods.sql',"select to_regclass('public.research_shared_campaigns') is not null present"),
 ('202610270001_experiment_builder.sql',"select to_regprocedure('public.research_builder_call(text,jsonb)') is not null present"),
 ('202610270002_experiment_builder_prompt.sql',"select exists(select 1 from agent_prompt_versions where id='6102d16d-c5cf-5f1c-8fc7-2df2899da972') present"),
 ('202610270003_builder_package_catalog.sql',"select to_regclass('public.research_builder_packages') is not null present"),
 ('202610270004_experiment_action_authority.sql',"select to_regprocedure('public.publish_agent_prompt_before_action_policy_v1(uuid,uuid,text,jsonb,text,text)') is not null present"),
 ('202610270005_builder_scheduling_window.sql',"select strpos(pg_get_functiondef('public.research_model_dispatch(text,jsonb)'::regprocedure),'245 seconds')>0 present")]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['inspect','migrate','prepare-host','status','freeze','evaluate','retrieve','collect','diagnose-operational','stop-qualification','review-diagnostic','reconcile-op-review','record-evaluations','publish','verify','recover-capture','capture-status']);a=p.parse_args()
 BASE.mkdir(parents=True,exist_ok=True);d=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');d.mkdir()
 report=dict(mode=a.mode,status='running',targets=r.target(),measured_charges_usd=None)
 def save():(d/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 save()
 try:
  if a.mode=='recover-capture':
   raw=(ROOT/'bin/recover_builder_capture_host.py').read_bytes();host='/var/lib/jumpserve-openclaw/builder-capture-recovery-'+r.sha(raw)+'.py'
   install="from pathlib import Path;import base64;p=Path("+repr(host)+");raw=base64.b64decode("+repr(base64.b64encode(raw).decode())+");assert not p.exists() or p.read_bytes()==raw;p.write_bytes(raw);p.chmod(0o644)"
   command='set -a\n. /etc/jumpserve-openclaw.env\nset +a\nrunuser -u jumpserve -- /opt/jumpserve/python/bin/python -B '+host
   report['ssm']=r.ssm(['python3.12 -c '+shlex.quote(install),command]);(BASE/'recovery-command.json').write_text(json.dumps(report['ssm']))
  elif a.mode=='capture-status':
   call=json.loads((BASE/'recovery-command.json').read_bytes());result=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id'])
   if result['Status']!='Success':raise RuntimeError('Capture recovery incomplete: '+result['Status']+' '+result.get('StandardErrorContent','')[-1000:])
   result=json.loads(result['StandardOutputContent']);source=BASE/'20261027T193546166732Z';archive=result['archive'];assert archive['sha256']==archive['retrieved_sha256'] and archive['path'].startswith('release-verification/experiment-builder/'+source.name+'/capture-recovery/')
   key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];request=urllib.request.Request('https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+archive['path'],headers={'apikey':key,'Authorization':'Bearer '+key})
   with r.prior.guard.OPEN.open(request,timeout=60) as response:raw=response.read(20000001)
   assert len(raw)<=20000000 and r.sha(raw)==archive['sha256'];(source/'originals.zip').write_bytes(raw)
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for item in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(item['path']))==item['sha256']
    (source/'host-report.json').write_bytes(z.read('report.json'))
   (source/'archive.json').write_text(json.dumps(archive,indent=2)+'\n');(source/'recovered-entry.json').write_text(json.dumps(result['recovered_entry'],indent=2)+'\n');report['archive']=archive;report['provider_calls_replayed']=0
  elif a.mode=='verify':
   report['deployed_sources']=r.prior.functions(d,True)
   report['security']=r.admin.query("select c.relname,c.relrowsecurity,has_table_privilege('anon',c.oid,'SELECT,INSERT,UPDATE,DELETE') anon_access,has_table_privilege('authenticated',c.oid,'SELECT,INSERT,UPDATE,DELETE') browser_access from pg_class c where c.oid in ('research_shared_campaigns'::regclass,'research_shared_campaign_members'::regclass,'research_builder_calls'::regclass,'research_builder_packages'::regclass) order by c.relname")
   assert len(report['security'])==4 and all(x['relrowsecurity'] and not x['anon_access'] and not x['browser_access'] for x in report['security'])
   report['prompts']=r.admin.query("select module_id,active_version_id from agent_prompt_settings where module_id in ('research-autonomy','research-experiment-builder') order by module_id")
   report['instance_id']=r.instance();assert report['instance_id']=='i-087f1493809643115'
  elif a.mode=='record-evaluations':
   report['evaluations']=[]
   for source in sorted(BASE.iterdir()):
    if not source.is_dir() or not (source/'host-report.json').exists() or not (source/'archive.json').exists():continue
    raw_report=json.loads((source/'host-report.json').read_bytes());archive=json.loads((source/'archive.json').read_bytes());assert archive['sha256']==archive['retrieved_sha256']
    if (source/'reviewed.json').exists():evaluation=json.loads((source/'reviewed.json').read_bytes());outcome=evaluation['status']
    else:evaluation=dict(kind='native-qualification-original',campaign=source.name,original_report=raw_report,archive=archive,publication_eligible=False,classification='Failed or operator-stopped development campaign; original runtime status is preserved.');outcome='failed-or-paused'
    raw=json.dumps(evaluation,sort_keys=True,separators=(',',':'));digest=r.sha(raw.encode());lit=r.admin.literal
    r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([lit('6102d16d-c5cf-5f1c-8fc7-2df2899da972')+'::uuid',lit(outcome),lit(raw),lit(digest),lit(json.dumps(archive))+'::jsonb',lit('Primary Codex AI implementer; nonindependent evaluation, not human review')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
    checked=r.admin.query('select encode(sha256(convert_to(report_raw,\'UTF8\')),\'hex\') sha256 from agent_prompt_evaluations where prompt_version_id=\'6102d16d-c5cf-5f1c-8fc7-2df2899da972\' and report_sha256='+lit(digest));assert checked==[dict(sha256=digest)]
    report['evaluations'].append(dict(campaign=source.name,outcome=outcome,sha256=digest,retrieved_sha256=digest))
  elif a.mode=='publish':
   selected=(BASE/'selected.txt').read_text().strip();assert selected.isalnum();source=BASE/selected
   evaluation=json.loads((source/'reviewed.json').read_bytes());frozen=json.loads((source/'frozen.json').read_bytes());archive=json.loads((source/'archive.json').read_bytes())
   assert evaluation['status']=='passed' and len(evaluation['cases'])==10 and all(x['passed'] and x['actual_answer_reviewed'] for x in evaluation['cases'])
   assert evaluation['prompt_sha256']==frozen['prompt_sha256'] and archive['sha256']==archive['retrieved_sha256']
   assert evaluation['local_release_checks_passed'] and evaluation['operational_release_checks_passed']
   assert evaluation['reviewer']['type']=='AI' and evaluation['reviewer']['independent'] is False
   lit=r.admin.literal;current=r.admin.query("select active_version_id from agent_prompt_settings where module_id='research-experiment-builder'")[0]['active_version_id']
   report['publication']=r.admin.query('select publish_agent_prompt('+','.join([lit(evaluation['prompt_id'])+'::uuid','null' if current is None else lit(current)+'::uuid',lit(evaluation['prompt_sha256']),lit(json.dumps(evaluation))+'::jsonb',lit('Codex AI implementer; user-authorized lab release, nonindependent'),lit('research-experiment-builder')])+')',read_only=False)
  elif a.mode=='reconcile-op-review':
   code="""import sys,json,urllib.request,urllib.error
sys.path.insert(0,'/opt/jumpserve/runtime')
import store
original=urllib.request.urlopen
def observed(*args,**kwargs):
 try:return original(*args,**kwargs)
 except urllib.error.HTTPError as e:
  value=json.loads(e.read(20000));print(json.dumps(dict(code=value.get('code'),message=value.get('message'))));raise
urllib.request.urlopen=observed
for study,identity,reason in [('c6490138-18f2-440b-be15-a1f4862ece13','1aab00aa-07ff-43ba-a5e5-63631ddf539e','Qualification preflight AttributeError before any provider request; original failed command retained.'),('41979451-d6ec-4396-af60-8754ad65acfd','c413e2eb-3956-4d62-8269-d698c268d55d','Qualification review adapter rejected the wrong decision schema; original provider SSE retained, no passing scientific review claimed.')]:
 result=store.request('/rest/v1/rpc/research_finish_idea_run','POST',dict(p_study=study,p_actor='4ee667d1-4cca-54ef-a3c1-e0a17de55da1',p_id=identity,p_status='failed',p_reason=reason,p_raw=None,p_output=None,p_usage=None,p_provenance=dict(raw_response_scope=dict(reconciliation='Recorded known release-adapter failure; no inference replay or successful review fabricated.')),p_messages=None))
 print(json.dumps(dict(id=result['id'],status=result['status'])))
"""
   report['ssm']=r.ssm(['set -a\n. /etc/jumpserve-openclaw.env\nset +a\nrunuser -u jumpserve -- /opt/jumpserve/python/bin/python -B -c '+shlex.quote(code)])
  elif a.mode=='review-diagnostic':
   report['runs']=r.admin.query("select r.id,r.study_id,r.status,r.reason,r.task,r.provenance,r.output,r.usage from research_idea_runs r join research_studies s on s.id=r.study_id where s.domain like 'Private deployment operational check 2026-10-27 builder-%' order by r.created_at")
   report['constraints']=r.admin.query("select conname,pg_get_constraintdef(oid) definition from pg_constraint where conrelid='research_idea_runs'::regclass")
   report['finish']=r.admin.query("select pg_get_functiondef('research_finish_idea_run(uuid,uuid,uuid,text,text,text,jsonb,jsonb,jsonb,jsonb)'::regprocedure) definition")
   report['finish_diagnostic']=r.admin.query("begin; create function pg_temp.builder_finish_diagnostic() returns jsonb language plpgsql as $f$ declare a public.research_idea_runs;msg text;ctx text;begin select r.* into strict a from research_idea_runs r join research_studies s on s.id=r.study_id where s.domain='Private deployment operational check 2026-10-27 builder-v4' and r.task='comprehension';perform public.research_finish_idea_run(a.study_id,a.actor_id,a.id,'failed','Retained invalid output from the release review adapter.',null,null,null,'{}',null);return jsonb_build_object('status','valid-rolled-back');exception when others then get stacked diagnostics msg=message_text,ctx=pg_exception_context;return jsonb_build_object('message',msg,'context',ctx);end $f$;select pg_temp.builder_finish_diagnostic();rollback;",read_only=False)
  elif a.mode=='stop-qualification':
   selected=(BASE/'selected.txt').read_text().strip();assert selected.isalnum()
   report['reason']='Repeated completed slots retained no source files; stop this development campaign, preserve unknown calls and investigate lost native continuation context.'
   report['ssm']=r.ssm(['systemctl kill --signal=SIGINT jumpserve-builder-qualification-'+selected.lower()+'.service'])
  elif a.mode=='diagnose-operational':
   original=sorted((ROOT/'.test-artifacts/experiment-builder-operational').glob('*/requested-records.json'))[-1]
   data=json.loads(original.read_bytes());lit=r.admin.literal
   call='public.research_append_bundle('+lit(data['study'])+'::uuid,'+lit(data['actor'])+'::uuid,'+lit(json.dumps(data['records']))+'::jsonb)'
   sql="begin; create function pg_temp.builder_diagnostic() returns jsonb language plpgsql as $f$ declare msg text;detail text;ctx text;begin perform "+call+";return jsonb_build_object('status','valid-rolled-back');exception when others then get stacked diagnostics msg=message_text,detail=pg_exception_detail,ctx=pg_exception_context;return jsonb_build_object('status','invalid-rolled-back','message',msg,'detail',detail,'context',ctx);end $f$;select pg_temp.builder_diagnostic() result;rollback;"
   report['diagnostic']=r.admin.query(sql,read_only=False)
  elif a.mode=='inspect':
   report['dispatches']=r.admin.query("select status,count(*) from research_model_dispatches group by status")
   report['migrations']=[dict(name=n,present=r.admin.query(q)[0]['present']) for n,q in MIGRATIONS]
   report['ssm']=r.ssm(['set -eu','df -h /opt/jumpserve','systemctl is-active jumpserve-openclaw.service','command -v docker || true','uname -m'])
  elif a.mode=='migrate':
   r.auth_maintenance_guard();report['migrations']=[]
   for n,q in MIGRATIONS:
    raw=(ROOT/'database'/n).read_bytes();present=r.admin.query(q)[0]['present'];entry=dict(name=n,sha256=r.sha(raw),status='present' if present else 'applying');report['migrations'].append(entry);save()
    if not present:r.admin.query(raw.decode(),read_only=False);assert r.admin.query(q)[0]['present'];entry['status']='applied';save()
  elif a.mode=='prepare-host':
   r.auth_maintenance_guard();dockerfile=(ROOT.parent/'jumpserve-back-end/research_workflow/experiment-builder.Dockerfile').read_bytes()
   code="from pathlib import Path;import base64;Path('/var/lib/jumpserve-builder-image/Dockerfile').write_bytes(base64.b64decode("+repr(base64.b64encode(dockerfile).decode())+"))"
   commands=['set -eu','test "$(id -u)" = 0','mkdir -p /var/lib/jumpserve-builder-image','dnf install -y docker','systemctl enable --now docker','usermod -aG docker jumpserve','python3.12 -c '+shlex.quote(code),
    'docker pull --platform linux/amd64 ubuntu:22.04 > /var/lib/jumpserve-builder-image/base-pull.log 2>&1',
    "docker image inspect ubuntu:22.04 --format '{{index .RepoDigests 0}}' > /var/lib/jumpserve-builder-image/base-digest.txt",
    'docker build --platform linux/amd64 --build-arg BASE_IMAGE="$(cat /var/lib/jumpserve-builder-image/base-digest.txt)" -t jumpserve-builder:release /var/lib/jumpserve-builder-image > /var/lib/jumpserve-builder-image/build.log 2>&1',
    'docker image inspect jumpserve-builder:release > /var/lib/jumpserve-builder-image/image.json',
    "docker image inspect jumpserve-builder:release --format '{{.Id}}' > /var/lib/jumpserve-builder-image/image-id.txt",
    'docker run --rm jumpserve-builder:release cat /jumpserve-image-packages.txt > /var/lib/jumpserve-builder-image/installed-packages.txt',
    "sed -i '/^OPENCLAW_BUILDER_IMAGE=/d;/^RESEARCH_BUILDER_ENABLED=/d' /etc/jumpserve-openclaw.env",
    "printf '%s\\n' \"OPENCLAW_BUILDER_IMAGE=$(cat /var/lib/jumpserve-builder-image/image-id.txt)\" 'RESEARCH_BUILDER_ENABLED=false' >> /etc/jumpserve-openclaw.env",
    'chmod 600 /etc/jumpserve-openclaw.env',
    "docker image inspect jumpserve-builder:release --format '{{.Id}} {{.Os}} {{.Architecture}}'",'systemctl restart jumpserve-openclaw.service']
   report['dockerfile_sha256']=r.sha(dockerfile);report['ssm']=r.ssm(commands);(BASE/'host-command.json').write_text(json.dumps(report['ssm']))
  elif a.mode=='status':
   original=json.loads((BASE/'host-command.json').read_bytes());result=r.aws('ssm','get-command-invocation','--command-id',original['command_id'],'--instance-id',original['instance_id']);report['command']=result
  elif a.mode=='freeze':
   cases=json.loads((ROOT/'test/experiment-builder-live-cases-v1.json').read_bytes());manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())
   prompt=r.admin.query("select id,system_prompt,research_context,content_sha256 from agent_prompt_versions where id='6102d16d-c5cf-5f1c-8fc7-2df2899da972'")[0]
   packet=dict(protocol='experiment-builder-live-evaluation-v1',input_version=cases['version'],cases=cases['cases'],runtime_files=manifest['files'],producer_sha256=r.sha((ROOT/'bin/experiment_builder_qualification_host.py').read_bytes()),prompt_id=prompt['id'],prompt_sha256=prompt['content_sha256'],system_prompt=prompt['system_prompt'],research_context=prompt['research_context'],maximum_calls=30,maximum_elapsed_seconds=1800,maximum_reserved_usd=30,frozen_at=dt.datetime.now(dt.timezone.utc).isoformat())
   amendment=json.loads((ROOT/'docs/experiment-builder-live-amendment-v5.json').read_bytes())
   for previous in amendment['prior_campaigns']:
    archive=json.loads((BASE/previous['id']/'archive.json').read_bytes());assert archive['sha256']==previous['archive_sha256']
   packet.update(amendment=amendment,prior_provider_calls=0,prior_campaign_provider_calls=25,prior_campaign_reserved_cents=2500)
   recovered=json.loads((BASE/amendment['continues_campaign']/'recovered-entry.json').read_bytes())
   assert recovered['source_archive']['sha256']==amendment['recovered_archive_sha256']
   packet['recovered_case']=recovered
   import sys
   sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
   import autonomy_model
   packet['blocker_contract']=dict(kinds=list(autonomy_model.BLOCKERS),details=list(autonomy_model.DETAILS),capacity_required_input=autonomy_model.LIMIT_INPUT)
   (d/'frozen.json').write_text(json.dumps(packet,indent=2)+'\n');(BASE/'selected.txt').write_text(d.name+'\n');report['frozen_sha256']=r.sha((d/'frozen.json').read_bytes());report['provider_calls']=0
  elif a.mode=='evaluate':
   r.auth_maintenance_guard();selected=(BASE/'selected.txt').read_text().strip();assert selected.isalnum();source=BASE/selected
   if (source/'dispatch.json').exists():raise RuntimeError('Qualification already dispatched; retrieve it, do not replay.')
   code=(ROOT/'bin/experiment_builder_qualification_host.py').read_bytes();packet=(source/'frozen.json').read_bytes();assert r.sha(code)==json.loads(packet)['producer_sha256']
   host='/var/lib/jumpserve-openclaw/builder-qualification/'+selected
   install="from pathlib import Path;import base64;p=Path("+repr(host)+");p.mkdir(parents=True,exist_ok=False);(p/'frozen.json').write_bytes(base64.b64decode("+repr(base64.b64encode(packet).decode())+"));(p/'producer.py').write_bytes(base64.b64decode("+repr(base64.b64encode(code).decode())+"))"
   cmd='set -eu\nset -a\n. /etc/jumpserve-openclaw.env\nset +a\nexport OPENCLAW_BUILDER_IMAGE="$(cat /var/lib/jumpserve-builder-image/image-id.txt)"\nrunuser -u jumpserve -- /opt/jumpserve/python/bin/python -B '+host+'/producer.py '+host
   report['ssm']=r.ssm(['set -eu','python3.12 -c '+shlex.quote(install),'chown -R jumpserve:jumpserve '+host,'systemd-run --unit=jumpserve-builder-qualification-'+selected.lower()+' --property=RuntimeMaxSec=1900 /bin/bash -c '+shlex.quote(cmd+' > '+host+'/run.log 2>&1')]);(source/'dispatch.json').write_text(json.dumps(report['ssm']));report['host_directory']=host
  elif a.mode=='retrieve':
   selected=(BASE/'selected.txt').read_text().strip();assert selected.isalnum();source=BASE/selected;host='/var/lib/jumpserve-openclaw/builder-qualification/'+selected
   code="from pathlib import Path;import json;p=Path("+repr(host)+");r=json.loads((p/'report.json').read_bytes()) if (p/'report.json').exists() else {};print(json.dumps(dict(status=r.get('status'),reason=r.get('reason'),cases=len(r.get('cases',[])),live_provider_calls=r.get('live_provider_calls'),slices=[dict(path=x.parent.name,status=json.loads(x.read_bytes()).get('status'),feedback=json.loads(x.read_bytes()).get('feedback'),calls=json.loads(x.read_bytes()).get('provider_calls')) for x in sorted(p.glob('*slice*/receipt.json'))],workspace_files=[str(x.relative_to(p)) for x in p.glob('builder-workspaces/*/workspace/**/*') if x.is_file()][:40],native_progress=[dict(type=i.get('type'),name=i.get('name'),arguments=str(i.get('arguments',''))[:500],output=str(i.get('output',''))[:500]) for x in p.glob('builder-workspaces/*/native-tool-history.json') for i in json.loads(x.read_bytes())][-12:],archive=json.loads((p/'archive.json').read_bytes()) if (p/'archive.json').exists() else None,log_tail=(p/'run.log').read_text()[-2000:] if (p/'run.log').exists() else None)))"
   report['ssm']=r.ssm(['python3.12 -c '+shlex.quote(code)]);(BASE/'retrieve-command.json').write_text(json.dumps(report['ssm']))
  elif a.mode=='collect':
   selected=(BASE/'selected.txt').read_text().strip();assert selected.isalnum();source=BASE/selected
   call=json.loads((BASE/'retrieve-command.json').read_bytes());result=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id'])
   if result['Status']!='Success':raise RuntimeError('Retrieval command is not complete.')
   report['result']=json.loads(result['StandardOutputContent']);archive=report['result'].get('archive')
   if archive:
    assert archive['bucket']=='research-workflow-raw' and archive['path'].startswith('release-verification/experiment-builder/'+selected+'/') and archive['sha256']==archive['retrieved_sha256']
    key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString']
    request=urllib.request.Request('https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+archive['path'],headers={'apikey':key,'Authorization':'Bearer '+key})
    with r.prior.guard.OPEN.open(request,timeout=60) as response:raw=response.read(20000001)
    assert len(raw)<=20000000 and r.sha(raw)==archive['sha256'];(source/'originals.zip').write_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
     for item in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(item['path']))==item['sha256']
     (source/'host-report.json').write_bytes(z.read('report.json'))
    (source/'archive.json').write_text(json.dumps(archive,indent=2)+'\n');report['independent_retrieval_verified']=True
  report['status']='complete'
 except Exception as e:report.update(status='failed',error=str(e));raise
 finally:save();print(json.dumps(dict(directory=str(d),**report),indent=2))
if __name__=='__main__':main()
