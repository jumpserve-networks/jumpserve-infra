"""Fixed-target, versioned recovery qualification and scoped release operations."""
import argparse,copy,datetime as dt,importlib.util,io,json,pathlib,subprocess,sys,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('prior_repair',ROOT/'bin/autonomous-repair-release.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
q=prior.q;r=q.r;m=q.m;BASE=ROOT/'.test-artifacts/builder-recovery-release-v1';q.BASE=BASE;q.ASSESSMENT=prior.STUDY

def pin():
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip(),'Commit the reviewed backend first'
 manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());names=sorted(set(manifest['files'])|{'dispatch_recovery.py','policies/builder-recovery-validation-v3.json'})
 value=dict(version=manifest['version']+1,source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip(),files={n:r.sha((BACK/'research_workflow'/n).read_bytes()) for n in names})
 q.save(ROOT/'research-workflow-runtime.json',value)
 return dict(source_revision=value['source_revision'],files=len(names),version=value['version'])

def freeze(out):
 r.auth_maintenance_guard();manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=BACK,text=True).strip() and subprocess.check_output(['git','rev-parse','HEAD'],cwd=BACK,text=True).strip()==manifest['source_revision']
 assert r.instance()=='i-087f1493809643115' and all(r.sha((BACK/'research_workflow'/n).read_bytes())==h for n,h in manifest['files'].items())
 oldname=(ROOT/'.test-artifacts/autonomous-repair-release-v1/selected.txt').read_text().strip();old=json.loads((ROOT/'.test-artifacts/autonomous-repair-release-v1'/oldname/'frozen.json').read_bytes())
 prompts=r.admin.query("select v.id,v.module_id,v.version,v.system_prompt,v.research_context,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id in ('research-autonomy','research-experiment-builder')")
 assert {p['module_id']:p for p in prompts}=={p['module_id']:p for p in old['prompts']},'Published prompt drift requires a new case review'
 context=copy.deepcopy(old['native_context']);context.pop('builder_feedback',None)
 empty=dict(task='building',claim=dict(description='Explicit software-only fixture: double a number read from a JSON spec file and preserve null. No networking or academic claim is being assessed.'),
  evaluation_case='Build a working versioned Python package from scratch in project/. Supply experiment.py, empty requirements.lock, system-packages.lock.json containing [], and build-evidence.json recording your actual checks and software-only limitations. Use standard library only. experiment.py must expose evaluate(spec_path), read the JSON file named by spec_path, and return exactly {value: double the input value or null, scope: software-development-only}. Its main reads the filename from JUMPSERVE_SPEC and writes JSON to the filename JUMPSERVE_OUTPUT. Check with the existing /workspace/control-input.json (value 7). Preserve missing/null and zero distinctly. Do not write candidate.json, execute a scientific campaign, alter limits, or claim a paper result. Write and execute the implementation rather than repeat read-only setup.',
  source_material=dict(origin='explicit-software-fixture',text='D(7)=14; D(0)=0; D(null)=null. Input and output paths are filenames; no measured paper data supplied.'),
  builder_feedback='There is no existing project implementation. Write project/experiment.py and its actual development check now, plus the three package metadata files. Inspect only missing essentials; no candidate.json is needed for this software qualification.',remaining_commitment_cents=1600,deadline_at='2026-11-04T20:25:04.587324Z')
 protocol=json.loads((ROOT/'docs/builder-recovery-release-protocol-v1.json').read_bytes())
 files={'research_workflow/'+n:(BACK/'research_workflow'/n).read_bytes() for n in manifest['files']}
 extras=['experiment-builder.Dockerfile','tests/check_experiment_builder_linux.py','tests/prepare_builder_image.py','tests/prepare_builder_vendor.py','tests/test_dispatch_recovery.py','tests/test_experiment_builder.py','tests/test_autonomous_repair.py','policies/builder-continuation-validation-v1.json','policies/builder-continuation-validation-v2.json']
 for n in extras:files['research_workflow/'+n]=(BACK/'research_workflow'/n).read_bytes()
 # Unit fixtures may inspect original non-active policies as negative controls.
 for path in (BACK/'research_workflow/policies').glob('*.json'):files['research_workflow/policies/'+path.name]=path.read_bytes()
 files['base_qualification.py']=(ROOT/'bin/builder_continuation_qualification_host.py').read_bytes();files['qualification.py']=(ROOT/'bin/builder_recovery_qualification_host.py').read_bytes()
 packet=dict(protocol=protocol,source_revision=manifest['source_revision'],runtime_manifest=manifest,source_files={n:r.sha(v) for n,v in files.items()},prompts=prompts,planner_cases=old['planner_cases'],native_context=context,empty_context=empty,original_program=old['original_program'],assessment=prior.STUDY,image='sha256:542c0bd0a512d3c18348103775a983a840067eaadb703276e432c17cc5308c64',frozen_at=r.stamp(),exposure='Exposed development cases, AI implementing reviewer; not independent, human or held-out validation')
 files['frozen.json']=json.dumps(packet,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode();q.save(out/'frozen.json',packet)
 files['artifact-manifest.json']=json.dumps([dict(path=n,sha256=r.sha(v),bytes=len(v)) for n,v in sorted(files.items())]).encode()
 stream=io.BytesIO()
 with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
  for n,v in sorted(files.items()):z.writestr(n,v)
 raw=stream.getvalue();(out/'candidate.zip').write_bytes(raw);path='qualification/builder-recovery-v1/'+out.name+'/'+r.sha(raw)+'.zip';m.storage(path,raw);assert m.storage(path)==raw
 q.save(out/'candidate.json',dict(path=path,sha256=r.sha(raw),retrieved_sha256=r.sha(raw),bytes=len(raw)));(BASE/'selected.txt').write_text(out.name+'\n')
 original=r.admin.query("select to_jsonb(w) workflow from research_autonomy_workflows w where study_id='"+prior.STUDY+"'")[0]['workflow'];q.save(out/'assessment-before.json',original)
 return dict(source_revision=manifest['source_revision'],files=len(manifest['files']),maximum_provider_calls=protocol['resources']['maximum_actual_provider_calls'],candidate_sha256=r.sha(raw))

def record(source):
 frozen=json.loads((source/'frozen.json').read_bytes());live=json.loads((source/'live.json').read_bytes());review=json.loads((source/'reviewed.json').read_bytes()) if (source/'reviewed.json').exists() else None
 pointer=json.loads((source/'host-status.json').read_bytes())['evidence.json'];assert r.sha(m.storage(pointer['path']))==pointer['sha256']
 passed=bool(review and review['passed'] and review['reviewer']['type']=='AI' and review['reviewer']['independent'] is False and review['source_revision']==frozen['source_revision'] and len(review['cases'])==4 and all(c['passed'] and c['actual_answer_reviewed'] and len(c['notes'])>=20 for c in review['cases']) and live['status']=='awaiting-substantive-review' and len(live['cases'])==4 and all(c['structural_checks_passed'] for c in live['cases']) and json.loads((source/'prepared.json').read_bytes())['status']=='passed' and json.loads((source/'native.json').read_bytes())['status']=='passed')
 outcome='passed' if passed else 'failed-or-paused';value=dict(protocol=frozen['protocol'],source_revision=frozen['source_revision'],outcome=outcome,live=live,review=review,archive=pointer,scientific_completion=False,prompt_publications_changed=False)
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False);sha=r.sha(raw.encode())
 for p in frozen['prompts']:
  r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(p['id'])+'::uuid',r.admin.literal(outcome),r.admin.literal(raw),r.admin.literal(sha),r.admin.literal(json.dumps(pointer))+'::jsonb',r.admin.literal('Codex implementing AI evaluator/reviewer; nonindependent exposed development qualification, not human or held-out')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
  rows=r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(p['id'])+'::uuid and report_sha256='+r.admin.literal(sha));assert len(rows)==1 and r.sha(rows[0]['report_raw'].encode())==sha
 result=dict(status=outcome,report_sha256=sha,archive=pointer);q.save(source/'evaluations-recorded.json',result);return result

def migrate(source):
 assert json.loads((source/'evaluations-recorded.json').read_bytes())['status']=='passed';r.auth_maintenance_guard()
 name='202610290001_builder_reconciliation.sql';raw=(ROOT/'database'/name).read_bytes();path='release-migrations/builder-recovery-v1/'+r.sha(raw)+'-'+name;m.storage(path,raw);assert m.storage(path)==raw
 present=r.admin.query("select to_regclass('public.research_model_reconciliations') is not null present")[0]['present']
 if not present:r.admin.query(raw.decode(),read_only=False)
 security=r.admin.query("select relrowsecurity,has_table_privilege('anon',c.oid,'SELECT') anon_read,has_table_privilege('authenticated',c.oid,'INSERT,UPDATE,DELETE') browser_write,has_table_privilege('service_role',c.oid,'INSERT,UPDATE,DELETE') direct_service_write from pg_class c where c.oid='public.research_model_reconciliations'::regclass")
 assert security==[dict(relrowsecurity=True,anon_read=False,browser_write=False,direct_service_write=False)]
 rpc=r.admin.query("select proname,has_function_privilege('anon',p.oid,'EXECUTE') anon,has_function_privilege('authenticated',p.oid,'EXECUTE') browser from pg_proc p where p.oid in ('public.research_model_reconcile(uuid,uuid,text,jsonb)'::regprocedure,'public.research_model_reconciliation_candidates(uuid)'::regprocedure)")
 assert len(rpc)==2 and all(not p['anon'] and not p['browser'] for p in rpc)
 result=dict(status='passed',name=name,sha256=r.sha(raw),present_before=present,security=security,rpc=rpc);q.save(source/'migration-applied.json',result);return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['pin','freeze','prepare','native','live','evidence','status','collect-status','collect','record-review','approve','migrate','verify-held','verify-active']);args=p.parse_args();BASE.mkdir(parents=True,exist_ok=True)
 out=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir();receipt=dict(mode=args.mode,status='running',started_at=r.stamp())
 try:
  receipt['targets']=r.target()
  if args.mode=='pin':result=pin()
  elif args.mode=='freeze':result=freeze(out)
  elif args.mode=='record-review':result=record(q.selected())
  elif args.mode=='approve':result=prior.approve(q.selected())
  elif args.mode=='migrate':result=migrate(q.selected())
  elif args.mode in ('verify-held','verify-active'):
   r.prior.PRIVATE.add('research_model_reconciliations');result=prior.verify(q.selected(),out,args.mode=='verify-active')
  elif args.mode in ('status','collect-status','collect'):result=getattr(q,args.mode.replace('-','_'))(q.selected());result.pop('cases',None)
  else:result=q.dispatch(q.selected(),args.mode)
  receipt.update(status='complete',result=result)
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:q.save(out/'receipt.json',receipt);print(json.dumps(dict(directory=str(out),**receipt)))
if __name__=='__main__':main()
