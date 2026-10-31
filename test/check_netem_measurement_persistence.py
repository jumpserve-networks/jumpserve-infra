"""Persist actual retained Linux measurements in isolated research SQL tables.

Retrospective software qualification import, not production paper evidence. Run
timestamps describe this import; original acquisition UTC bounds are unavailable.
No model, new networking invocation, cloud service or production database call.
"""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import uuid
import check_research_ideas_database as f
from check_autonomy_completion_database import DurableStorage
import netem_iperf,network_execution,store,workflow

def verify(path):
 path=Path(path).resolve()
 if path.name!='netem-persistence-manifest.json' or not path.is_relative_to(f.ROOT/'.test-artifacts/research-ideas/database'):raise ValueError('Fixed local persistence manifest required.')
 saved=json.loads(path.read_bytes());f.DATABASE=saved['database'];f.query.__defaults__=(f.DATABASE,None);f.files=DurableStorage(path.parent/'durable-storage');store.request=f.transport
 query=dict(study_id='eq.'+saved['study']);runs=store.rows('runs',query);rows=store.rows('measurements',query);configs=store.rows('configurations',query);artifacts=store.rows('artifacts',query)
 assert len(runs)==3 and len(rows)==75 and len(configs)==1
 assert configs[0]['details']['test_config']==saved['config']
 assert {r['details']['replication'] for r in rows}=={0,1,2} and {r['details']['loss_pct'] for r in rows}=={0,1,2,5,10}
 for a in artifacts:
  raw=store.artifact_bytes(saved['study'],a['id'],maximum=3_000_000);assert len(raw)==a['byte_count'] and workflow.digest(raw)==a['sha256']
 for r in runs:assert r['provenance']['timestamp_scope']=='Import processing only; original acquisition UTC start/end were not recorded.'
 (path.parent/'netem-persistence-restart.json').write_bytes(workflow.canonical(dict(passed=True,pid=os.getpid(),runs=3,measurements=75,configurations=1,hash_verified_artifacts=len(artifacts),new_acquisitions=0)))

def main():
 f.report.update(protocol='autonomy-recovery-execution-v1',design=__doc__,provider_calls=0,new_experiment_invocations=0,production_writes=0)
 try:
  selected=json.loads((f.ROOT.parent/'jumpserve-back-end/.test-artifacts/executable-methods/linux/full-grid-selected.json').read_bytes());source=Path(selected['directory']).resolve()
  if not source.is_relative_to(f.ROOT.parent/'jumpserve-back-end/.test-artifacts/executable-methods/linux'):raise ValueError('A retained local Linux qualification is required.')
  raw_report=(source/'report.json').read_bytes();assert workflow.digest(raw_report)==selected['report_sha256'];report=json.loads(raw_report);assert report['passed'] and report['observations']==75
  for a in report['artifacts']:
   raw=(source/a['name']).read_bytes();assert len(raw)==a['bytes'] and workflow.digest(raw)==a['sha256']
  original_protocol=json.loads((source/'protocol.json').read_bytes());config=original_protocol['config'];assert config['loss_levels_pct']==[0,1,2,5,10] and config['duration_seconds']==30 and original_protocol['replications']==3
  f.files=DurableStorage(f.DIRECTORY/'durable-storage');f.bootstrap()
  study=f.uid();store.rpc('research_create_study',dict(p_actor=f.ACTOR,p_id=study,p_document=workflow.paper_details(dict(title='Retrospective Linux networking persistence qualification',paper_url=None,study_kind='idea',domain='Networking software verification',scope='Preserve actual development measurements; no paper claim assessment.'))))
  artifacts={}
  for path in sorted(source.rglob('*')):
   if not path.is_file():continue
   name=str(path.relative_to(source));raw=path.read_bytes();record=store.artifact(study,f.ACTOR,raw,str(uuid.uuid5(uuid.UUID(study),'original:'+name)),'application/octet-stream',dict(kind='linux-netem-qualification-original',filename=name,transformation='none; unchanged original captured bytes',original_report_sha256=workflow.digest(raw_report)))
   store.append(study,f.ACTOR,'artifacts',record);artifacts[name]=record
  source_raw=Path(netem_iperf.__file__).read_bytes();assert workflow.digest(source_raw)==json.loads((source/'spec.json').read_bytes())['implementation_sha256']
  implementation=store.artifact(study,f.ACTOR,source_raw,f.uid(),'text/x-python',dict(kind='linux-netem-qualification-implementation',transformation='none; exact implementation used by retained invocations'));store.append(study,f.ACTOR,'artifacts',implementation)
  identity='retained-full-loss-grid';p=workflow.numerical_protocol(implementation['sha256'],'throughput_mbit_s','Mbit/s',0,[dict(identity=identity,details=dict(test_config=config))])
  p.update(data_origin='new-empirical',planned_units=3,prior_exposure='All retained development observations were available before this retrospective import. No prospective scientific evaluation.',replication_unit='One original five-condition invocation. All three invocations share one Docker host; no independent-host inference.',coverage_limits='Software persistence qualification only; no causal claim or paper conclusion. Original acquisition UTC times were not recorded.')
  p['metrics']=[dict(name=name,units=units,planned_observations=5) for name,units in netem_iperf.METRICS.items()];p['resource_limits']['max_observations']=25
  p['input_versions']=[dict(identity='retained-qualification-protocol.json',sha256=artifacts['protocol.json']['sha256']),dict(identity='netem_iperf.py',sha256=implementation['sha256'])]
  # Exercise the ordinary idea-protocol gate. These readiness judgments are
  # explicitly synthetic software fixtures, never independent scientific review.
  value=dict({field:'Explicit software-retention fixture; no scientific finding or actual model review.' for field in f.ideas.FIELDS},protocol=p)
  packet=f.ideas.save(study,f.ACTOR,dict(action='save',request_id=f.uid(),supersedes_id=None,document=value,reason='Retrospective development evidence persistence.'))
  prompt=f.uid();f.query("insert into agent_prompt_versions(id,module_id,version,system_prompt,research_context,published_at,created_by,updated_by) values("+f.sql_text(prompt)+",'research-verification','synthetic-netem-retention-fixture','Explicit synthetic SQL fixture','No actual provider evaluation or scientific review',clock_timestamp(),'synthetic fixture','synthetic fixture');update agent_prompt_settings set active_version_id="+f.sql_text(prompt)+" where module_id='research-verification'")
  reviews={}
  for role in ('comprehension','critic'):
   review=f.rpc('research_begin_idea_run',dict(p_study=study,p_actor=f.ACTOR,p_user='software-fixture@example.invalid',p_id=f.uid(),p_packet=packet['id'],p_task=role,p_session=None,p_prompt=prompt,p_model='synthetic-software-provider',p_request=dict(task=role,fixture=True),p_provenance=dict(packet_sha256=packet['sha256'],context_policy='fresh-packet-only',history_messages=0)))
   answer=dict(summary='Synthetic software readiness only; preserve original observations and missing times.',questions=[],findings=[],verdict='ready')
   f.rpc('research_finish_idea_run',dict(p_study=study,p_actor=f.ACTOR,p_id=review['id'],p_status='complete',p_reason=None,p_raw=workflow.canonical(answer).decode(),p_output=answer,p_usage=dict(tokens=None,measured_charges_usd=None),p_provenance={},p_messages=None));reviews[role]=review['id']
  f.ideas.accept(study,f.ACTOR,dict(action='accept',request_id=f.uid(),packet_id=packet['id'],comprehension_run_id=reviews['comprehension'],critic_run_id=reviews['critic'],reason='Synthetic software qualification approval; no AI or human scientific review.'))
  p=dict(p,idea_packet_id=packet['id'],idea_packet_sha256=packet['sha256'])
  protocol=workflow.validate_record('protocols',dict(id=f.uid(),version=1,supersedes_id=None,document=p,sha256=workflow.digest(workflow.canonical(p)),frozen_at=workflow.now(),registration_kind='retrospective-import',amendment_reason='Import unchanged observed development measurements; no prospective registration or historical experiment timestamp is asserted.'))
  configuration=workflow.validate_record('configurations',dict(id=f.uid(),identity=identity,details=dict(test_config=config),input_versions=p['input_versions'],requested_resources=dict(qualification_protocol_artifact_id=artifacts['protocol.json']['id'])))
  campaign=workflow.validate_record('campaigns',dict(id=f.uid(),protocol_id=protocol['id'],followup_of=None,title='Retained full-grid development acquisition',stage='retrospective-import',experiment_type='new-measurement',adapter='network-execution-v1',planned_units=3,coverage_limits=p['coverage_limits']))
  store.append_bundle(study,f.ACTOR,[dict(kind=k,record=r) for k,r in [('protocols',protocol),('configurations',configuration),('campaigns',campaign)]])
  for replication in range(3):
   raw=(source/f'trial-{replication}/output.json').read_bytes();original_spec=json.loads((source/f'trial-{replication}/spec.json').read_bytes());assert original_spec['config']==config and original_spec['replication']==replication
   began=workflow.now();spec=dict(runner=netem_iperf.VERSION,config=config,configuration_identity=identity,replication=replication,limits=dict(source='Retained original development qualification; no new dispatch.'))
   run,rows,summaries=network_execution.evidence(dict(id=f.uid()),campaign,dict(protocol,document=p),spec,raw,dict(status='completed',started_at=began,ended_at=workflow.now(),artifacts=[dict(id=artifacts[f'trial-{replication}/output.json']['id'],sha256=workflow.digest(raw))],resources=dict(new_acquisitions=0,source_platform=report['platform'],emulated=report['emulated'])))
   run.update(configuration_id=configuration['id'],analysis_version='qualification-netem-import-v1');run['provenance'].update(timestamp_scope='Import processing only; original acquisition UTC start/end were not recorded.',original_acquisition_started_at=None,original_acquisition_ended_at=None,original_spec_artifact_id=artifacts[f'trial-{replication}/spec.json']['id'],derived_import_spec_sha256=run['input_sha256'])
   entries=[dict(kind='runs',record=run),*[dict(kind='measurements',record=r) for r in rows],*[dict(kind='summaries',record=r) for r in summaries]]
   (f.DIRECTORY/('netem-import-entries-'+str(replication)+'.json')).write_bytes(workflow.canonical(entries))
   store.append_bundle(study,f.ACTOR,entries);store.append_bundle(study,f.ACTOR,entries)
   f.rejects(lambda:store.append_bundle(study,f.ACTOR,[dict(kind='measurements',record=dict(rows[0],units='incorrect-units'))]))
   f.rejects(lambda:f.rpc('research_append',dict(p_study=study,p_actor=f.ACTOR,p_kind='runs',p_record=dict(run,unexpected_field='Must not be silently discarded'))))
  manifest=f.DIRECTORY/'netem-persistence-manifest.json';manifest.write_bytes(workflow.canonical(dict(database=f.DATABASE,study=study,config=config)))
  result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--verify',str(manifest)],capture_output=True,timeout=60);(f.DIRECTORY/'netem-restart-stdout.bin').write_bytes(result.stdout);(f.DIRECTORY/'netem-restart-stderr.bin').write_bytes(result.stderr)
  assert result.returncode==0,'Separate-process readback failed; retained stderr identifies the exact blocker.'
  restarted=json.loads((f.DIRECTORY/'netem-persistence-restart.json').read_bytes());assert restarted['pid']!=os.getpid()
  (f.DIRECTORY/'database-snapshot.json').write_bytes(workflow.canonical({name:store.rows(name,dict(study_id='eq.'+study,limit=1000)) for name in ('protocols','configurations','campaigns','runs','measurements','summaries','artifacts')}))
  f.report.update(passed=True,study_id=study,original_report_sha256=workflow.digest(raw_report),readback=restarted,scope='Actual isolated PostgreSQL research relations and durable local Storage transport fixture. Remote Supabase Storage and production assessment execution remain unverified.')
 except Exception as error:f.report.update(passed=False,error=str(error),traceback=traceback.format_exc());raise
 finally:
  path=f.DIRECTORY/'netem-persistence-report.json';path.write_bytes(workflow.canonical(f.report));print(json.dumps(dict(report=str(path),passed=f.report.get('passed'))))

if __name__=='__main__':
 if len(sys.argv)==3 and sys.argv[1]=='--verify':verify(sys.argv[2])
 elif len(sys.argv)==1:main()
 else:raise SystemExit('Only the fixed local persistence verification is supported.')
