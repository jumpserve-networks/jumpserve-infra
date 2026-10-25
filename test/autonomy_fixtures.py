"""Explicit synthetic provider/source/Storage/auth fixtures, never research data."""
import copy,hashlib,json,uuid
from decimal import Decimal
from pathlib import Path
import check_research_ideas_database as f
import autonomy,autonomy_model as model,preparation,workflow

URL='https://example.org/autonomy-software-fixture.pdf'
def pdf_bytes():
 content=b'BT /F1 12 Tf 40 200 Td (Explicit autonomous software fixture; no academic claims.) Tj ET'
 objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 400] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream']
 raw=b'%PDF-1.4\n';offsets=[]
 for number,body in enumerate(objects,1):offsets.append(len(raw));raw+=str(number).encode()+b' 0 obj\n'+body+b'\nendobj\n'
 start=len(raw);raw+=b'xref\n0 6\n0000000000 65535 f \n'
 for offset in offsets:raw+=('%010d 00000 n \n'%offset).encode()
 return raw+b'trailer\n<< /Root 1 0 R /Size 6 >>\nstartxref\n'+str(start).encode()+b'\n%%EOF\n'

def plan():
 source=str(uuid.uuid5(uuid.NAMESPACE_URL,'autonomy-software-source'))
 reviewer=dict(identity='Synthetic software fixture',type='AI',independence='Synthetic inputs and model output; no actual scientific review')
 original=pdf_bytes()
 s=dict(id=source,citation='Synthetic matched-cell fixture, not an academic paper',source_url=URL,retrieved_url=None,kind='software-fixture',role='Exercise persistence and missing data only',retrieved_version='fixture-v1',sha256=workflow.digest(original),byte_count=len(original),access_status='software-fixture',review_status='retrieved-unreviewed',review_definition='No substantive source reviewed',examined='Synthetic fixture declarations',unexamined='No real source paper',retrieval_attempts=[],reviewer=reviewer,findings='No scientific findings',limitations='Not empirical data or a paper assessment')
 records=[dict(kind='sources',record=s)];campaigns=[]
 for index,name in enumerate(('eventual-agreement','eventual-discrepancy','missing-equipment')):
  claim=str(uuid.uuid5(uuid.NAMESPACE_URL,'autonomy-software-claim:'+name))
  description='Synthetic '+name+' claim: latency is 10 ms under fixed configuration.'
  records.append(dict(kind='claims',record=dict(id=claim,source_id=source,location='Synthetic cell '+str(index),description=description,claim_type='numerical',scope=dict(population='One declared synthetic cell; no population inference'),metrics=[dict(name='latency',units='ms')],priority=3)))
  for trial in range(2):
   row=dict(observation_id='cell-'+str(index),configuration_identity='fixed',metric='latency',units='ms',value=10,status='recorded',reason=None)
   observed=[] if trial==0 else [dict(row,value=12 if index==1 else 10)]
   raw=workflow.canonical(dict(published=[dict(row,source_id=source,location='Synthetic cell '+str(index),extraction='Synthetic reference; not a published value')],observed=observed))
   p=workflow.numerical_protocol(workflow.digest(raw),'latency','ms',0.1,[dict(identity='fixed',details=dict(input_kind='synthetic software fixture',trial=trial))])
   p.update(hypotheses=description,prior_exposure='Exposed synthetic development inputs; no held-out or scientific validation.',data_origin='software-fixture')
   p['metrics'][0]['planned_observations']=1
   campaigns.append(dict(key=name+'-'+str(trial),campaign=dict(title='Synthetic '+name+' check '+str(trial),stage='main',experiment_type='reanalysis',adapter='matched-numeric-v1',planned_units=1,coverage_limits='One matched synthetic cell only'),protocol=p,claim_ids=[claim],execution_mode='automatic',raw_input=raw.decode(),dependencies=[],priority=3,rationale='Exercise actual queue arithmetic and persistence with synthetic original inputs.',exclusive_resources=[]))
 return dict(schema_version=1,plan_id='autonomy-software-fixture-v1',title='Synthetic autonomous verification fixture',paper_urls=[URL],provenance=dict(producer='Explicit local software fixture',source_version='fixture-v1',prior_exposure='Exposed development inputs',limitations='Synthetic source/provider/auth/Storage; no cloud or scientific result'),records=records,campaigns=campaigns)

def publish_fixture():
 if model.PROMPT_VERSION in ('research-autonomy-v7','research-autonomy-v8'):
  candidate='v8' if model.PROMPT_VERSION=='research-autonomy-v8' else 'v7';case_version='v2' if candidate=='v8' else 'v1';case_path=f.ROOT/('test/autonomy-followup-cases-'+case_version+'.json')
  seed=json.loads((f.ROOT/('database/seed-autonomy-'+candidate+'.json')).read_bytes());cases=json.loads(case_path.read_bytes());manifest=json.loads((f.ROOT/'research-workflow-runtime.json').read_bytes())
  for name,sha in manifest['files'].items():assert hashlib.sha256((f.ROOT.parent/'jumpserve-back-end/research_workflow'/name).read_bytes()).hexdigest()==sha,'Local runtime source changed: '+name
  sha=f.query('select content_sha256 from agent_prompt_versions where id='+f.sql_text(seed['id']))
  report=dict(protocol=cases['protocol'],analysis_version=autonomy.VERSION,module_id=model.MODULE,prompt_version_id=seed['id'],prompt_version=seed['version'],prompt_content_sha256=sha,evaluation_kind='actual-model-development',live_provider_calls=len(cases['cases']),model_id=model.MODEL,
   cases_sha256=hashlib.sha256(case_path.read_bytes()).hexdigest(),input_sha256=manifest['files'],request_manifest_sha256='a'*64,integration_report_sha256='b'*64,integration_passed=True,
   fixture_notice='Synthetic local SQL guard declarations only; not actual provider evaluation or production publication.',
   evaluator=dict(identity='Explicit synthetic evaluator fixture',type='AI',independent=False),reviewer=dict(identity='Explicit synthetic reviewer fixture',type='AI',independent=False,passed=True),
   cases=[dict(name=c['name'],passed=True,status='complete',raw_answer_reviewed=True,rendered_answer_reviewed=True,output_sha256='b'*64,provider_response_sha256='c'*64) for c in cases['cases']])
  if candidate=='v8':report.update(judgment_criteria_sha256=hashlib.sha256((f.ROOT/'test/autonomy-followup-judgments-v3.json').read_bytes()).hexdigest(),review_amendment='autonomy-bounded-followups-amendment-v4',original_strict_checks_passed=8,original_strict_checks_total=9,intermediate_only_cases=['earlier-partial-discrepancy'],original_evaluation_report_sha256='c'*64)
  if candidate=='v8':report.update(completion_report_sha256='d'*64,completion_report=dict(version='autonomy-followup-completion-v2',passed=True,reviewer=dict(passed=True),decision_protocol_sha256=hashlib.sha256((f.ROOT/'docs/autonomy-bounded-followups-amendment-v5.md').read_bytes()).hexdigest(),input_sha256=manifest['files'],fixture_sha256='e'*64,frozen_inputs_sha256='f'*64,cases=[dict(passed=True,raw_answer_reviewed=True,rendered_answer_reviewed=True,output=dict(assessment_label='inconclusive'))]))
  if candidate=='v8':report.update(trajectory_policy_sha256=hashlib.sha256((f.ROOT/'test/autonomy-trajectory-policy-v1.json').read_bytes()).hexdigest(),trajectory_report_sha256='a'*64,trajectory_report=dict(version='autonomy-trajectory-evaluation-v1',limits=dict(max_attempts_per_claim=25,max_paper_committed_cents=10000,max_elapsed_seconds=604800),status='complete',reviewer=dict(passed=True),input_sha256=manifest['files'],attempts_used=4,committed_cents=600,checks=dict(exact_prompts_retained=True,scoped_reads=True,evidence_decisions=True,authorization_preserved=True,no_unknown_call_replay=True),terminal_status='assessed',reason='Synthetic publication guard only; four turns are allowed.',cases=[dict(number=i+1,passed=True,raw_answer_reviewed=True,rendered_answer_reviewed=True,output=dict(action='assess',assessment_label='reproduced',coverage_complete=True) if i==3 else dict(action='inspect')) for i in range(4)]))
  if candidate=='v8':
   for case in report['trajectory_report']['cases']:case['status']='complete'
   # Exercise the unchanged historical publication guard with its own frozen
   # profile, while separately identifying the actual development code tested.
   # These synthetic declarations never establish a new model evaluation.
   profile=json.loads((f.ROOT/'test/autonomy-publication-runtime-v8.json').read_bytes())
   report['fixture_tested_working_tree_sha256']=manifest['files']
   report['fixture_tested_analysis_version']=autonomy.VERSION
   report['analysis_version']='research-autonomy-v2'
   report['fixture_publication_profile']='Historical released v27; synthetic SQL guard exercise, not a current model evaluation.'
   report['input_sha256']=profile['files']
   report['completion_report']['input_sha256']=profile['files']
   report['trajectory_report']['input_sha256']=profile['files']
  return dict(p_version_id=seed['id'],p_expected_active_version_id=None,p_expected_content_sha256=sha,p_report=report,p_actor='Synthetic local publication guard exercise only',p_module_id=model.MODULE)
 seed=json.loads((f.ROOT/'database/seed-autonomy-v6.json').read_bytes());lock=json.loads((f.ROOT/'test/autonomy-implementation-lock-v6.json').read_bytes())
 released=json.loads((f.ROOT/'test/autonomy-evidence-lock-v1.json').read_bytes())
 for name,sha in released['files'].items():
  assert hashlib.sha256((f.ROOT.parent/'jumpserve-back-end/research_workflow'/name).read_bytes()).hexdigest()==sha,'Renew local source lock before testing changed implementation: '+name
 sha=f.query('select content_sha256 from agent_prompt_versions where id='+f.sql_text(seed['id']))
 report=dict(protocol='autonomous-assessment-protocol-v1',analysis_version=autonomy.VERSION,module_id=model.MODULE,prompt_version_id=seed['id'],prompt_version=seed['version'],prompt_content_sha256=sha,
  evaluation_kind='actual-model-development',live_provider_calls=19,evidence_live_provider_calls=1,evaluation_revision='lossless-evidence-v1',evidence_evaluation_report_sha256='a'*64,evidence_inputs_sha256=released['inputs_sha256'],model_evaluation_live_provider_calls=16,integration_live_provider_calls=2,report_kind='composite-model-and-context-integration',model_evaluation_report_sha256='e'*64,integration_evaluation_report_sha256='f'*64,released_input_sha256=released['files'],prior_live_provider_calls=14,prior_failed_provider_calls=5,new_provider_calls=5,reused_answer_count=9,recovery_source_sha256='d'*64,release_amendment='autonomous-assessment-production-amendment-v11',model_id=model.MODEL,cases_sha256=lock['cases_sha256'],request_manifest_sha256=lock['request_manifest_sha256'],response_channel_sha256=lock['response_channel_sha256'],input_sha256=lock['files'],
  fixture_notice='Synthetic SQL-guard declarations only; not an actual provider evaluation or production publication.',evaluator=dict(identity='Explicit synthetic evaluator fixture',type='AI',independent=False),reviewer=dict(identity='Explicit synthetic reviewer fixture',type='AI',independent=False,passed=True),
  cases=[dict(name=c['name'],passed=True,status='complete',raw_answer_reviewed=True,rendered_answer_reviewed=True,output_sha256='b'*64,provider_response_sha256='c'*64) for c in json.loads((f.ROOT/'test/autonomy-evaluation-cases-v2.json').read_bytes())['cases']+json.loads((f.ROOT/'test/autonomy-integration-inputs-v1.json').read_bytes())['cases']+[dict(name='lossless-192-record-assessment')]])
 payload=dict(p_version_id=seed['id'],p_expected_active_version_id=None,p_expected_content_sha256=sha,p_report=report,p_actor='Synthetic local publication guard exercise only',p_module_id=model.MODULE)
 return payload

def provider(request):
 context=json.loads(request['messages'][-1]['content'][0]['text']);stage=context['task']
 out=dict(action='blocked',reason='missing-required-inputs',blockers=[],claims=[],check_id=None,proposal=None,ready=None,coverage_complete=False,assessment_label=None,evidence_ids=[])
 if stage=='discover':
  quote=context['source_chunk']['text'].strip()
  out.update(action='discover',reason='text-extracted',claims=[dict(page=context['source_chunk']['page'],quote=quote,claim_type='operational')])
  if context.get('paper_metadata_requested'):out['paper_metadata']=dict(title=dict(text=quote,quote=quote,page=context['source_chunk']['page']),domain=dict(text='Software testing',quote=quote,page=context['source_chunk']['page']))
 elif stage=='paper-review-selection':
  prior=[item for name in ('central_claims','testable_findings') for item in context['prior_shortlist'][name]]
  incoming=[dict(claim_id=c['id'],label=c['description'][:100]) for c in context['candidates']]
  items=list({c['claim_id']:c for c in prior+incoming}.values())
  out.update(action='discover',reason='text-extracted',paper_review_selection=dict(central_claims=items[:1],testable_findings=items[1:16],rationale='Explicit synthetic organization fixture; not a model quality evaluation.'))
 elif stage=='planning':
  if 'missing-equipment' in context['claim']['description']:
   out.update(blockers=[dict(kind='equipment',detail='unavailable-equipment',required_input='Applicable authorized instrument or archived measurement data')])
  elif context['registered_checks']:
   out.update(action='choose-check',check_id=context['registered_checks'][0]['id'],reason='retained-check')
  else:out.update(blockers=[dict(kind='implementation',detail='unavailable-implementation',required_input='A separately reviewed applicable experiment')])
 elif stage in ('comprehension','critic'):out.update(action='review',ready=True,coverage_complete=True,reason='ready-within-scope')
 elif stage=='assessment':
  finding=context.get('controller_numeric_check')
  if not finding:out.update(action='assess',assessment_label='inconclusive',reason='evidence-incomplete')
  else:out.update(action='assess',assessment_label=finding['label'],coverage_complete=True,reason='matched-numeric-check')
 return dict(stopReason='tool_use',output=dict(message=dict(role='assistant',content=[dict(toolUse=dict(toolUseId='explicit-fixture',name='submit_assessment_step',input=out))])),usage=dict(inputTokens=100,outputTokens=50,totalTokens=150))

def registered(study):
 value=plan();return (value,workflow.canonical(value)) if preparation.matches_paper(value,study) else ORIGINAL_REGISTERED(study)
ORIGINAL_REGISTERED=preparation.registered
