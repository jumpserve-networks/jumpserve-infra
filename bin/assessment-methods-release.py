"""Fixed-target method qualification/release and an explicitly authorized rerun.

Private material is retained under ignored artifacts; credentials are never printed.
"""
import argparse,base64,datetime as dt,hashlib,importlib.util,io,json,os,pathlib,shlex,subprocess,urllib.error,urllib.request,uuid,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/assessment-methods-release-v1'
ORIGINAL='b5a2a984-0ce7-44c9-a7a5-f12a87559c7f'
PDF_SHA='77becb203ef79c5e5d0b69ee9cfc5553e5680d2c44128aaa6b8f2c545d533617'
API='https://regphejnlvfpyokpniny.supabase.co'

def storage(path,raw=None):
    key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString']
    request=urllib.request.Request(API+'/storage/v1/object/research-workflow-raw/'+path,data=raw,headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/octet-stream'},method='POST' if raw is not None else 'GET')
    try:
        with r.prior.guard.OPEN.open(request,timeout=60) as response:return response.read(20000001)
    except (urllib.error.URLError,TimeoutError):
        if raw is None:raise
        # Content-addressed, no-overwrite writes are reconciled by an exact GET.
        read=urllib.request.Request(API+'/storage/v1/object/research-workflow-raw/'+path,headers={'apikey':key,'Authorization':'Bearer '+key})
        with r.prior.guard.OPEN.open(read,timeout=60) as response:restored=response.read(20000001)
        if restored!=raw:raise RuntimeError('Storage write is unconfirmed; retain the original object identity.')
        return b''

def save(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n');path.chmod(0o600)
def current():return BASE/(BASE/'selected.txt').read_text().strip()

def inspect(out):
    kinds=('studies','study_owners','autonomy_workflows','autonomy_tasks','sources','claims','artifacts','paper_reviews')
    data={}
    for kind in kinds:
        field='id' if kind=='studies' else 'study_id'
        data[kind]=[v['record'] for v in r.admin.query('select to_jsonb(t) record from public.research_'+kind+' t where '+field+'='+r.admin.literal(ORIGINAL)+'::uuid')]
    assert len(data['studies'])==len(data['study_owners'])==len(data['autonomy_workflows'])==1
    study=data['studies'][0];assert study['study_kind']=='paper' and study['paper_upload']['sha256']==PDF_SHA
    claims={t['claim_id'] for t in data['autonomy_tasks'] if t['claim_id']}
    assert len(claims)==9 and not any(t['status'] in ('queued','running','waiting') for t in data['autonomy_tasks'])
    save(out/'private-snapshot.json',data)
    originals={}
    for artifact in data['artifacts']:
        if artifact['provenance'].get('kind') not in ('derived-pdf-text','paper-original-upload'):continue
        assert artifact['storage_path']==ORIGINAL+'/'+artifact['sha256']
        raw=storage(artifact['storage_path']);assert len(raw)==artifact['byte_count'] and r.sha(raw)==artifact['sha256']
        path=out/('original-'+artifact['id']);path.write_bytes(raw);path.chmod(0o600)
        originals[artifact['id']]=dict(file=path.name,sha256=r.sha(raw),bytes=len(raw),kind=artifact['provenance']['kind'])
    save(out/'originals.json',originals)
    prompts=r.admin.query("select v.id,v.module_id,v.version,v.system_prompt,v.research_context,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on s.active_version_id=v.id where s.module_id in ('research-autonomy','research-experiment-builder')")
    assert {p['version'] for p in prompts}=={'research-autonomy-v10','research-experiment-builder-v2'}
    save(out/'published-prompts.json',prompts)
    return dict(original_assessment=ORIGINAL,selected_claims=9,originals_verified=len(originals),paper_sha256=PDF_SHA,old_status=data['autonomy_workflows'][0]['status'])

def freeze(out):
    result=inspect(out)
    files=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())['files']
    files={n:r.sha((BACK/'research_workflow'/n).read_bytes()) for n in [*files,'autonomy_methods.py']}
    packet=dict(protocol='autonomy-methods-release-v1',frozen_at=r.stamp(),runtime_files=files,
        original_assessment=ORIGINAL,paper_sha256=PDF_SHA,
        protocol_sha256=r.sha((ROOT/'docs/autonomy-methods-release-protocol-v1.md').read_bytes()),
        maximum_live_calls=30,maximum_elapsed_seconds=3600,
        evaluator=dict(identity='Codex implementation/evaluation author',type='AI',independent=False))
    if (out/'followup.json').exists():
        followup=json.loads((out/'followup.json').read_bytes());packet.update(followup_of=followup['previous_campaign'],aggregate_started_at=followup.get('aggregate_started_at'),previous_provider_calls=followup['previous_provider_calls'],maximum_live_calls=followup.get('maximum_aggregate_calls',30)-followup['previous_provider_calls'],maximum_elapsed_seconds=followup['remaining_seconds'],case_selection=followup.get('case_selection',['source-injection']))
    env=r.aws('lambda','get-function-configuration','--function-name',r.functions()['autonomy'])['Environment']['Variables']
    packet['execution_environment']={k:v for k,v in env.items() if k.startswith('NETWORK_') and (k.endswith('_FUNCTION') or k.endswith('_POLICY_SHA256'))}
    save(out/'frozen.json',packet)
    stage={('research_workflow/'+n):(BACK/'research_workflow'/n).read_bytes() for n in files}
    stage.update({p.name:p.read_bytes() for p in out.iterdir() if p.is_file()})
    stage['qualify.py']=(ROOT/'bin/assessment_methods_qualification_host.py').read_bytes()
    stage['release-protocol.md']=(ROOT/'docs/autonomy-methods-release-protocol-v1.md').read_bytes()
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(stage.items()):z.writestr(name,raw)
        z.writestr('candidate-manifest.json',json.dumps([dict(path=n,sha256=r.sha(raw),bytes=len(raw)) for n,raw in sorted(stage.items())]))
    raw=buffer.getvalue();path='qualification/autonomy-methods-v1/'+out.name+'/candidate-'+r.sha(raw)+'.zip'
    storage(path,raw);assert storage(path)==raw
    save(out/'candidate.json',dict(path=path,sha256=r.sha(raw),bytes=len(raw)))
    (BASE/'selected.txt').write_text(out.name+'\n')
    return dict(result,candidate_sha256=r.sha(raw),runtime_files=len(files))

def prepare(source):
    assert not (source/'prepare-command.json').exists()
    item=json.loads((source/'candidate.json').read_bytes());host='/var/lib/jumpserve-openclaw/assessment-methods-v1/'+source.name
    install='''import io,json,pathlib,sys,zipfile
sys.path.insert(0,'/opt/jumpserve/runtime')
import store
from workflow import digest
raw=store.request('/storage/v1/object/research-workflow-raw/'+OBJECT,raw=True);assert digest(raw)==HASH
root=pathlib.Path(DEST);root.mkdir(parents=True,exist_ok=False)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
 for entry in json.loads(z.read('candidate-manifest.json')):
  name=pathlib.PurePosixPath(entry['path']);assert not name.is_absolute() and '..' not in name.parts
  data=z.read(entry['path']);assert digest(data)==entry['sha256'];p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
'''.replace('OBJECT',repr(item['path'])).replace('HASH',repr(item['sha256'])).replace('DEST',repr(host))
    command=r.ssm(['set -eu','set -a','. /etc/jumpserve-openclaw.env','set +a','/opt/jumpserve/python/bin/python -B -c '+shlex.quote(install),'chown -R jumpserve:jumpserve '+host])
    save(source/'prepare-command.json',dict(command,host=host));return command

def plan_rerun(source):
    """Build a reviewable, atomic copy plan; do not create database records yet."""
    import sys
    sys.path.insert(0,str(BACK/'research_workflow'))
    import autonomy
    from workflow import FIELDS,canonical,validate_record
    data=json.loads((source/'private-snapshot.json').read_bytes());old=data['studies'][0];owner=data['study_owners'][0]['owner_id']
    assert old['id']==ORIGINAL and old['paper_upload']['sha256']==PDF_SHA
    review=data['paper_reviews'][0];assert review['status']=='confirmed'
    request_path=BASE/'new-assessment-request.json'
    if request_path.exists():request=json.loads(request_path.read_bytes())
    else:
        request=dict(id=str(uuid.uuid4()),source_assessment=ORIGINAL,maximum_spend_usd=100,authorized_by='Application owner via Codex conversation; new assessment and backend release explicitly requested.',requested_at=r.stamp())
        save(request_path,request)
    target=request['id'];assert request['source_assessment']==ORIGINAL and request['maximum_spend_usd']==100
    uid=lambda key:str(uuid.uuid5(uuid.UUID(target),key))
    tasks=[t for t in data['autonomy_tasks'] if t['claim_id']];assert len(tasks)==9
    selected={t['claim_id'] for t in tasks};claims=[c for c in data['claims'] if c['id'] in selected];assert len(claims)==9
    source_ids={c['source_id'] for c in claims};sources=[s for s in data['sources'] if s['id'] in source_ids]
    assert len(sources)==1 and sources[0]['sha256']==PDF_SHA
    original_index=json.loads((source/'originals.json').read_bytes());pdf=next((i,v) for i,v in original_index.items() if v['kind']=='paper-original-upload');text=next((i,v) for i,v in original_index.items() if v['kind']=='derived-pdf-text')
    source_map={s['id']:uid('source-copy:'+s['id']) for s in sources};claim_map={c['id']:uid('claim-copy:'+c['id']) for c in claims}
    pdf_id=uid('paper-original:'+PDF_SHA);text_id=uid('text-copy:'+text[0]);stamp=request['requested_at']
    artifact=lambda identity,item,kind,**extra:dict(id=identity,sha256=item['sha256'],byte_count=item['bytes'],storage_path=target+'/'+item['sha256'],media_type='application/pdf' if kind=='paper-original-upload' else 'application/json',provenance=dict(kind=kind,source_study_id=ORIGINAL,source_artifact_id=pdf[0] if kind=='paper-original-upload' else text[0],transformation='Byte-identical owner-authorized archived input copy; no new extraction or substantive source review.',**extra),verified_at=stamp)
    pdf_artifact=artifact(pdf_id,pdf[1],'paper-original-upload',input_origin='owner-authorized-rerun',sha256=PDF_SHA)
    text_artifact=artifact(text_id,text[1],'derived-pdf-text',original_sha256=PDF_SHA,original_artifact_id=pdf_id)
    entries=[dict(kind='artifacts',record=validate_record('artifacts',text_artifact))]
    for s in sources:
        record={k:s[k] for k in FIELDS['sources']};record.update(id=source_map[s['id']])
        record['retrieval_attempts']=record['retrieval_attempts']+[dict(method='Owner-authorized reuse of the previously verified original; destination round-trip receipt is retained separately before admission.',authorized_at=stamp,source_assessment=ORIGINAL,sha256=PDF_SHA,original_artifact_id=pdf_id)]
        record['limitations']+=' Reused source inventory and extraction from assessment '+ORIGINAL+'; no new independent source review.'
        entries.append(dict(kind='sources',record=validate_record('sources',record)))
    for c in claims:
        record={k:c[k] for k in FIELDS['claims']};record.update(id=claim_map[c['id']],source_id=source_map[c['source_id']],scope=dict(c['scope'],prior_assessment=ORIGINAL,prior_claim_id=c['id'],reuse_scope='Exact previously selected statement; no new model extraction or scientific finding.'))
        entries.append(dict(kind='claims',record=validate_record('claims',record)))
    contexts={source_map[s['id']]:dict(source_id=source_map[s['id']],text_artifact_id=text_id,original_artifact_id=pdf_id,rerun_source=dict(assessment=ORIGINAL,pdf_sha256=PDF_SHA,scope='Archived inputs only; earlier measurements/verdicts are not new empirical observations.')) for s in sources}
    seeds=[dict(id=uid('autonomous-claim:'+claim_map[c['id']]),claim_id=claim_map[c['id']],context=contexts[source_map[c['source_id']]]) for c in claims]
    selection={k:[claim_map[c] for c in review['metadata']['owner_selection'][k] if c in claim_map] for k in ('central_claims','testable_findings')}
    assert set(selection['central_claims']+selection['testable_findings'])==set(claim_map.values())
    def mapped(value):
        if isinstance(value,str):return claim_map.get(value,value)
        if isinstance(value,list):return [mapped(v) for v in value]
        if isinstance(value,dict):return {k:mapped(v) for k,v in value.items()}
        return value
    metadata=dict(authors=review['metadata'].get('authors',[]),prior_confirmed_assessment=ORIGINAL,operator_provenance=request['authorized_by'],source_inventory_reused=True,new_source_review=False)
    organization=review['metadata'].get('selection')
    if organization:
        metadata['selection']=mapped(organization)
        for group in ('central_claims','testable_findings'):
            metadata['selection'][group]=[v for v in metadata['selection'][group] if v['claim_id'] in claim_map.values()]
        metadata['selection'].update(candidate_count=9,cursor=9,status='ready',reuse_scope='Filtered archived grouping of the nine previously selected statements; no new grouping model call.')
    paper={k:old[k] for k in ('title','paper_url','paper_upload','domain','scope','study_kind','origin_module')}
    initial=autonomy.start_payload(target,paper);initial['initial_prompt']=canonical(dict(json.loads(initial['initial_prompt']),rerun_authorization=request,source_input_scope='Reuse the exact nine previously confirmed source statements and original input bytes. Develop missing designs and execute new tests; never treat previous numerical or empirical results as newly acquired.')).decode()
    quote=lambda value:r.admin.literal(json.dumps(value,separators=(',',':'),ensure_ascii=False))+'::jsonb'
    sql='begin;\nselect pg_advisory_xact_lock(hashtextextended(\'research-autonomy-v1\',0));\n'
    sql+="do $rerun$ begin\n if exists(select 1 from public.research_autonomy_workflows where study_id='"+target+"'::uuid) then raise exception 'New assessment already exists; reconcile retained identities instead of creating a replacement';end if;\n end $rerun$;\n"
    sql+='select public.research_paper_upload(\'copy\','+r.admin.literal(owner)+'::uuid,'+r.admin.literal(target)+'::uuid,jsonb_set('+quote(dict(paper=paper,source_study_id=ORIGINAL,artifact=pdf_artifact))+',\'{artifact,verified_at}\',to_jsonb(clock_timestamp())));\n'
    sql+='select public.research_append_bundle('+r.admin.literal(target)+'::uuid,'+r.admin.literal(owner)+'::uuid,jsonb_set('+quote(entries)+',\'{0,record,verified_at}\',to_jsonb(clock_timestamp())));\n'
    sql+='select public.research_autonomy_control(\'start\','+r.admin.literal(owner)+'::uuid,'+r.admin.literal(target)+'::uuid,'+quote(initial)+');\n'
    sql+='insert into public.research_paper_reviews(study_id,status,title,domain,metadata,seeds,coverage,reason) values ('+r.admin.literal(target)+'::uuid,\'ready\','+r.admin.literal(old['title'])+','+r.admin.literal(old['domain'])+','+quote(metadata)+','+quote(seeds)+','+quote(dict(source_assessment=ORIGINAL,selected_statements=9,complete_source_review=False,scope='Archived confirmed selected inventory reused by explicit owner instruction; scientific coverage remains incomplete.'))+','+r.admin.literal('Owner authorized a new assessment of the exact previously selected statements; no fresh extraction or review is claimed.')+');\n'
    sql+='update public.research_autonomy_tasks set status=\'finished\',reason='+r.admin.literal('Reused owner-confirmed source inventory; no new AI extraction or independent review.')+',context='+quote(dict(source_assessment=ORIGINAL,source_inventory_reused=True,selected_claims=9,complete_source_review=False))+',updated_at=clock_timestamp() where study_id='+r.admin.literal(target)+'::uuid and claim_id is null;\n'
    sql+='insert into public.research_autonomy_events(study_id,event,details) values ('+r.admin.literal(target)+'::uuid,\'owner-authorized-new-assessment\','+quote(dict(request,source_pdf_sha256=PDF_SHA,source_statements=9,execution_origin='Service operator acting on explicit owner instruction through Codex; not an authenticated browser submission.',initial_prompt_sha256=r.sha(initial['initial_prompt'].encode())))+');\n'
    sql+='select public.research_paper_review(\'confirm\','+r.admin.literal(owner)+'::uuid,'+r.admin.literal(target)+'::uuid,'+quote(dict(title=old['title'],domain=old['domain'],revision=1,claim_ids=list(claim_map.values()),selection=selection))+');\ncommit;\n'
    (source/'new-assessment.sql').write_text(sql);(source/'new-assessment.sql').chmod(0o600)
    save(source/'rerun-plan.json',dict(id=target,paper=paper,request=request,sql_sha256=r.sha(sql.encode()),originals=[dict(source_file=pdf[1]['file'],storage_path=pdf_artifact['storage_path'],sha256=PDF_SHA),dict(source_file=text[1]['file'],storage_path=text_artifact['storage_path'],sha256=text[1]['sha256'])],mapped_claims=claim_map,selected_claims=9))
    return dict(new_assessment_id=target,selected_claims=9,maximum_spend_usd=100,source_assessment_unchanged=True,sql_sha256=r.sha(sql.encode()),status='planned-not-created')

def create_rerun(source,dry_run=False):
    plan=json.loads((source/'rerun-plan.json').read_bytes());sql=(source/'new-assessment.sql').read_text()
    assert r.sha(sql.encode())==plan['sql_sha256'] and plan['selected_claims']==9
    if not dry_run:
        verified=json.loads((BASE/'release-verified.json').read_bytes())
        assert verified['status']=='passed' and verified['campaign']==source.name
        assert r.admin.query('select id from public.research_studies where id='+r.admin.literal(plan['id'])+'::uuid')==[],'Assessment already exists: inspect its original jobs rather than create another run.'
        copies=[]
        for item in plan['originals']:
            raw=(source/item['source_file']).read_bytes();assert r.sha(raw)==item['sha256']
            storage(item['storage_path'],raw);restored=storage(item['storage_path']);assert restored==raw
            copies.append(dict(sha256=r.sha(raw),retrieved_sha256=r.sha(restored),bytes=len(raw),verified_at=r.stamp()))
        save(source/'new-assessment-original-copy-receipt.json',copies)
    # The atomic transaction uses the normal owner-bound copy/append/start and
    # confirmation functions. Nothing bypasses RLS or immutable evidence guards.
    before={kind:[v['record'] for v in r.admin.query('select to_jsonb(t) record from public.research_'+kind+' t where '+('id' if kind=='studies' else 'study_id')+'='+r.admin.literal(ORIGINAL)+'::uuid')] for kind in ('studies','study_owners','autonomy_workflows','autonomy_tasks','sources','claims','artifacts','paper_reviews')}
    if dry_run:sql=sql.removesuffix('commit;\n')+'rollback;\n'
    r.admin.query(sql,read_only=False)
    after={kind:[v['record'] for v in r.admin.query('select to_jsonb(t) record from public.research_'+kind+' t where '+('id' if kind=='studies' else 'study_id')+'='+r.admin.literal(ORIGINAL)+'::uuid')] for kind in before}
    normalize=lambda value:json.dumps({k:sorted(v,key=lambda row:row.get('id',row.get('study_id'))) for k,v in value.items()},sort_keys=True,separators=(',',':'))
    assert normalize(before)==normalize(after),'Original assessment changed unexpectedly; preserve receipts and investigate.'
    new=r.admin.query('select s.id,w.status,w.max_spend_cents,w.max_attempts,w.committed_cents,w.deadline_at,(select count(*) from public.research_autonomy_tasks t where t.study_id=s.id and t.claim_id is not null) claims from public.research_studies s join public.research_autonomy_workflows w on w.study_id=s.id where s.id='+r.admin.literal(plan['id'])+'::uuid')
    if dry_run:assert not new
    else:assert len(new)==1 and new[0]['max_spend_cents']==10000 and new[0]['max_attempts'] is None and new[0]['claims']==9
    result=dict(id=plan['id'],mode='rollback-dry-run' if dry_run else 'created',original_unchanged=True,original_snapshot_sha256=r.sha(normalize(before).encode()),new=new,sql_sha256=plan['sql_sha256'])
    save(source/('rerun-dry-run.json' if dry_run else 'rerun-created.json'),result)
    return result

def record_qualification(source):
    review=json.loads((ROOT/'docs/autonomy-methods-actual-answer-review-v1.json').read_bytes())
    assert review['status']=='passed' and review['campaign']==source.name and review['reviewer']['type']=='AI' and not review['reviewer']['independent']
    reports=[];campaign=source
    while True:
        frozen=json.loads((campaign/'frozen.json').read_bytes());report=json.loads((campaign/'qualification-report.json').read_bytes())
        raw=(campaign/'qualification.zip').read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for entry in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(entry['path']))==entry['sha256']
        reports.append(dict(campaign=campaign.name,status=report['status'],provider_calls=report['live_provider_calls'],archive_sha256=r.sha(raw),runtime_files=frozen['runtime_files']))
        if not frozen.get('followup_of'):break
        campaign=BASE/frozen['followup_of']
    assert sum(v['provider_calls'] for v in reports)<=50 and len(reports)==4
    assert reports[0]['status']=='awaiting-substantive-review'
    files={str(p.relative_to(BASE)):p.read_bytes() for p in BASE.rglob('*') if p.is_file() and p.name in ('qualification.zip','frozen.json','candidate.json','followup.json','qualification-report.json','archive-recovery.json','receipt.json','rerun-dry-run.json','rerun-dry-run-reference.json','arithmetic-candidate-source-check.json')}
    for label,path in dict(backend_tests=BACK/'.test-artifacts/autonomy-methods-v1/release-backend-unit-v4.log',infrastructure_tests=ROOT/'.test-artifacts/autonomy-methods-v1-infra-unit.log',database_checks=ROOT/'.test-artifacts/research-ideas/database/20261028T022109194960Z/method-window-validation.json',migration=ROOT/'database/202610280001_data_only_model_window.sql',runtime_manifest=ROOT/'research-workflow-runtime.json').items():files['validation/'+label+path.suffix]=path.read_bytes()
    files['actual-answer-review.json']=json.dumps(review,sort_keys=True).encode()
    files['release-protocol.md']=(ROOT/'docs/autonomy-methods-release-protocol-v1.md').read_bytes()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in sorted(files.items()):z.writestr(name,raw)
        z.writestr('artifact-manifest.json',json.dumps([dict(path=n,sha256=r.sha(v),bytes=len(v)) for n,v in files.items()]))
    raw=stream.getvalue();assert len(raw)<20000000
    path='qualification/autonomy-methods-v1/final/'+r.sha(raw)+'.zip';storage(path,raw);restored=storage(path);assert restored==raw
    archive=dict(bucket='research-workflow-raw',path=path,sha256=r.sha(raw),retrieved_sha256=r.sha(restored),bytes=len(raw),public=False)
    evaluations=[]
    for item in reversed(reports):
        passed=item['campaign']==source.name
        value=dict(protocol='autonomy-methods-release-v1',kind='versioned-controller-policy-and-native-builder-development-qualification',status='passed' if passed else 'failed-or-paused',campaign=item,review=review if passed else None,history=reports,archive=archive,historical_prompt_publication_unchanged=True,reviewer=review['reviewer'],measured_charges_usd=None,subscription_allocation_usd=None)
        raw=json.dumps(value,sort_keys=True,separators=(',',':'));sha=r.sha(raw.encode())
        for prompt in ('6117e5c5-84ce-5c31-aaa7-0d1d3522e62e','dfab5ecb-b8b9-5ad3-8771-f28a06b53b27'):
            r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(prompt)+'::uuid',r.admin.literal('passed' if passed else 'failed-or-paused'),r.admin.literal(raw),r.admin.literal(sha),r.admin.literal(json.dumps(archive))+'::jsonb',r.admin.literal('Codex AI implementer/evaluator/reviewer; nonindependent development checks, not human or held-out validation')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
            rows=r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(prompt)+'::uuid and report_sha256='+r.admin.literal(sha));assert len(rows)==1 and r.sha(rows[0]['report_raw'].encode())==sha
            evaluations.append(dict(prompt_version_id=prompt,report_sha256=sha,campaign=item['campaign'],outcome=value['status']))
    result=dict(status='passed',campaign=source.name,archive=archive,evaluations=evaluations,aggregate_provider_calls=sum(v['provider_calls'] for v in reports));save(BASE/'qualification-recorded.json',result);return result

def migrate_window():
    r.auth_maintenance_guard()
    sql=(ROOT/'database/202610280001_data_only_model_window.sql').read_bytes()
    query="select pg_get_functiondef('public.research_model_dispatch(text,jsonb)'::regprocedure) definition"
    before=r.admin.query(query)[0]['definition'];already="else interval '235 seconds' end" in before
    if not already:r.admin.query(sql.decode(),read_only=False)
    after=r.admin.query(query)[0]['definition'];assert "else interval '235 seconds' end" in after and "else interval '100 seconds' end" not in after
    return dict(status='passed',migration='202610280001_data_only_model_window.sql',sha256=r.sha(sql),present_before=already,definition_sha256=r.sha(after.encode()),private_function_grants_preserved=True)

def verify_release(source):
    qualification=json.loads((BASE/'qualification-recorded.json').read_bytes());manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())
    assert qualification['status']=='passed' and qualification['campaign']==source.name
    assert manifest['files']==json.loads((source/'frozen.json').read_bytes())['runtime_files']
    checks=[json.loads(p.read_bytes()) for p in sorted((ROOT/'.test-artifacts/builder-production-v2').glob('*/receipt.json'))]
    activated=next(c for c in reversed(checks) if c['mode']=='activated' and c['status']=='complete' and c['functions'][0]['source_files_verified']==50)
    executor=next(c for c in reversed(checks) if c['mode']=='executor' and c['status']=='complete' and c['function']==activated['functions'][0]['built_executor'].split(':function:')[1].rsplit(':',1)[0])
    receipts=sorted((ROOT/'.test-artifacts/openclaw-release').glob('*/receipt.json'))
    host=next(json.loads(p.read_bytes()) for p in reversed(receipts) if json.loads(p.read_bytes()).get('mode')=='host-check')
    assert host['started_at']>json.loads((source/'qualification-report.json').read_bytes())['ended_at']
    invocation=r.aws('ssm','get-command-invocation','--command-id',host['ssm']['command_id'],'--instance-id',host['ssm']['instance_id'])
    assert invocation['Status']=='Success' and 'Pinned host source hashes verified: 50' in invocation['StandardOutputContent']
    definition=r.admin.query("select pg_get_functiondef('public.research_model_dispatch(text,jsonb)'::regprocedure) definition")[0]['definition'];assert "else interval '235 seconds' end" in definition
    grants=r.admin.query("select has_function_privilege('anon','public.research_model_dispatch(text,jsonb)','EXECUTE') anon,has_function_privilege('authenticated','public.research_model_dispatch(text,jsonb)','EXECUTE') authenticated");assert grants==[dict(anon=False,authenticated=False)]
    assert r.instance()=='i-087f1493809643115'
    result=dict(status='passed',campaign=source.name,verified_at=r.stamp(),backend_revision=manifest['source_revision'],runtime_files_verified=50,qualification=qualification,functions=activated['functions'],security=activated['security'],polling=activated['polling'],host_check=dict(command_id=host['ssm']['command_id'],status=invocation['Status'],stdout_sha256=r.sha(invocation['StandardOutputContent'].encode())),executor_source_verification=True,dispatch_definition_sha256=r.sha(definition.encode()),conditional_gaps=['No Google-authenticated browser submission is represented by this operator-authorized rerun.','The clean native software control does not establish paper experiment execution or scientific findings.'],measured_charges_usd=None)
    save(BASE/'release-verified.json',result);return {k:v for k,v in result.items() if k not in ('qualification','functions','security')}

def verify_held(source,out):
    r.auth_maintenance_guard()
    qualification=json.loads((BASE/'qualification-recorded.json').read_bytes());assert qualification['status']=='passed' and qualification['campaign']==source.name
    functions=r.prior.functions(out,True);assert len(functions)==3 and all(len(f['source_hashes'])==50 for f in functions)
    assert r.aws('cloudformation','describe-stacks','--stack-name','JumpServeBenchmarkStack')['Stacks'][0]['StackStatus']=='UPDATE_COMPLETE'
    save(BASE/'held-release-verified.json',dict(status='passed',campaign=source.name,functions=functions,verified_at=r.stamp()))
    return dict(status='passed',functions=len(functions),files_per_function=50,admission_held=True)

def observe_rerun(source,out):
    plan=json.loads((source/'rerun-plan.json').read_bytes());identity=r.admin.literal(plan['id'])+'::uuid'
    result=dict(id=plan['id'],observed_at=r.stamp(),workflow=r.admin.query('select status,max_spend_cents,committed_cents,max_attempts,deadline_at,updated_at from research_autonomy_workflows where study_id='+identity),tasks=r.admin.query('select id,claim_id,stage,status,label,attempts,reason,updated_at from research_autonomy_tasks where study_id='+identity+' order by created_at,id'),turns=r.admin.query('select id,stage,status,request_sha256,prompt_version_id,model_id,usage,estimated_cents,reason,created_at from research_autonomy_turns where study_id='+identity+' order by created_at'),queue=r.admin.query('select id,status,reason,created_at,updated_at from research_queue_jobs where study_id='+identity+' order by created_at'),runs=r.admin.query('select id,status,created_at from research_runs where study_id='+identity+' order by created_at'),measurements=r.admin.query('select status,count(*) count from research_measurements where study_id='+identity+' group by status'),scientific_assessments=r.admin.query('select claim_id,label,created_at from research_assessments where study_id='+identity+' order by created_at'),measured_charges_usd=None)
    save(out/'private-progress.json',result)
    return dict(id=plan['id'],workflow=result['workflow'],task_statuses=[dict(claim_id=t['claim_id'],stage=t['stage'],status=t['status'],label=t['label'],attempts=t['attempts'],reason=t['reason']) for t in result['tasks']],turns=len(result['turns']),turn_statuses={s:sum(t['status']==s for t in result['turns']) for s in {t['status'] for t in result['turns']}},queue=result['queue'],runs=result['runs'],measurements=result['measurements'],scientific_assessments=result['scientific_assessments'],measured_charges_usd=None)

def record_release(source,out):
    verified=json.loads((BASE/'release-verified.json').read_bytes());created=json.loads((source/'rerun-created.json').read_bytes())
    browser_path=sorted((BASE/'browser').glob('*/report.json'))[-1];browser=json.loads(browser_path.read_bytes())
    assert verified['status']=='passed' and verified['campaign']==source.name and created['mode']=='created' and created['original_unchanged'] and browser['passed'] and browser['assessment_id']==created['id']
    files={}
    for p in BASE.rglob('*'):
        if p.is_file() and p.suffix in ('.json','.png') and p.name not in ('private-snapshot.json','published-prompts.json','rerun-plan.json'):
            files['operator/'+str(p.relative_to(BASE))]=p.read_bytes()
    for dirname in ('openclaw-release','builder-production-v2'):
        for p in (ROOT/'.test-artifacts'/dirname).glob('*/*'):
            if p.is_file() and p.parent.name>='20261028T024126796590Z' and (p.name in ('receipt.json','cdk.log','outputs.json','parameter-comparison.json') or p.suffix=='.zip'):
                files[dirname+'/'+str(p.relative_to(ROOT/'.test-artifacts'/dirname))]=p.read_bytes()
    for name in ('docs/autonomy-methods-v1-validation.md','docs/autonomy-methods-actual-answer-review-v1.json','docs/autonomy-methods-qualification-artifacts-v1.json','docs/autonomy-methods-release-protocol-v1.md','research-workflow-runtime.json','bin/assessment-methods-release.py','bin/verify_assessment_methods_browser.mjs','database/202610280001_data_only_model_window.sql'):
        files[name]=(ROOT/name).read_bytes()
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for name,raw in files.items():z.writestr(name,raw)
        z.writestr('artifact-manifest.json',json.dumps([dict(path=n,sha256=r.sha(v),bytes=len(v)) for n,v in files.items()]))
    raw=stream.getvalue();assert len(raw)<20000000
    path='release-verification/autonomy-methods-v1/'+r.sha(raw)+'.zip';storage(path,raw);restored=storage(path);assert restored==raw
    with zipfile.ZipFile(io.BytesIO(restored)) as z:
        for item in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(item['path']))==item['sha256']
    archive=dict(bucket='research-workflow-raw',path=path,sha256=r.sha(raw),retrieved_sha256=r.sha(restored),bytes=len(raw),public=False)
    value=dict(protocol='autonomy-methods-release-v1',kind='operational-release-and-authorized-rerun-verification',status='passed-software-gates-background-scientific-assessment-running',backend_revision=verified['backend_revision'],release_verification=verified,browser=browser,rerun=created,archive=archive,reviewer=dict(identity='Codex AI implementation/evaluation/review author',type='AI',independent=False,human=False),scientific_completion=False,measured_charges_usd=None,subscription_allocation_usd=None,unallocated_existing_worker_cost_usd=None)
    raw=json.dumps(value,sort_keys=True,separators=(',',':'));sha=r.sha(raw.encode())
    for prompt in ('6117e5c5-84ce-5c31-aaa7-0d1d3522e62e','dfab5ecb-b8b9-5ad3-8771-f28a06b53b27'):
        r.admin.query('insert into agent_prompt_evaluations(prompt_version_id,outcome,report_raw,report_sha256,original_artifacts,recorded_by) values('+','.join([r.admin.literal(prompt)+'::uuid',r.admin.literal('passed'),r.admin.literal(raw),r.admin.literal(sha),r.admin.literal(json.dumps(archive))+'::jsonb',r.admin.literal('Codex AI implementer; nonindependent operational release verification, not human review or scientific completion')])+') on conflict(prompt_version_id,report_sha256) do nothing',read_only=False)
        restored=r.admin.query('select report_raw from agent_prompt_evaluations where prompt_version_id='+r.admin.literal(prompt)+'::uuid and report_sha256='+r.admin.literal(sha));assert len(restored)==1 and r.sha(restored[0]['report_raw'].encode())==sha
    result=dict(status=value['status'],backend_revision=verified['backend_revision'],assessment_id=created['id'],maximum_spend_usd=100,original_unchanged=True,archive={k:archive[k] for k in ('sha256','retrieved_sha256','bytes','public')},evaluation_sha256=sha,scientific_completion=False,conditional_gaps=verified['conditional_gaps'],measured_charges_usd=None)
    save(ROOT/'docs/autonomy-methods-production-status-v1.json',result);return result

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['inspect','freeze','amend','followup','repair-followup','native-continuation','contract-amend','prepare','start','status','collect','diagnose','retain','retained','record-qualification','migrate-window','verify-held','verify-release','plan-rerun','dry-run-rerun','create-rerun','observe-rerun','record-release']);args=parser.parse_args()
    BASE.mkdir(parents=True,exist_ok=True);out=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir()
    report=dict(protocol='autonomy-methods-release-v1',mode=args.mode,status='running',started_at=r.stamp(),targets=r.target())
    try:
        if args.mode=='inspect':report['inspection']=inspect(out)
        elif args.mode=='freeze':
            assert not (BASE/'selected.txt').exists(),'A campaign is already frozen; retain it before making a versioned amendment.'
            report['candidate']=freeze(out)
        elif args.mode=='amend':
            previous=current();assert not (previous/'start-command.json').exists() and not (previous/'prepare-command.json').exists(),'Only a pre-dispatch amendment is supported; preserve actual calls and declare a new follow-up otherwise.'
            save(out/'pre-live-amendment.json',dict(previous_campaign=previous.name,previous_provider_calls=0,reason='Reject builder reference directory/file symlinks before trusted source writes.',maximum_aggregate_provider_calls=30))
            report['candidate']=freeze(out)
        elif args.mode=='contract-amend':
            previous=current();assert not (previous/'prepare-command.json').exists() and not (previous/'start-command.json').exists()
            for name in ('native-resume.json','followup.json','resume-checkpoint.zip'):(out/name).write_bytes((previous/name).read_bytes())
            resume=json.loads((out/'native-resume.json').read_bytes());resume['feedback']+=' The current runner-contract.json now supplies the exact executable spec fields and unchanged generated_package wrapper reference. Executable spec metrics have ONLY name and units; planned_observations belongs only to the protocol. Amend experiment.py accordingly and run the actual unchanged wrapper with the real file contract, retaining outputs. The earlier development spec with planned_observations was not the executable contract.';save(out/'native-resume.json',resume)
            save(out/'pre-live-contract-amendment.json',dict(previous_campaign=previous.name,provider_calls=0,reason='Expose exact spec fields and unchanged wrapper; refresh trusted contract after restoring the original checkpoint.'))
            report['candidate']=freeze(out)
        elif args.mode=='native-continuation':
            previous=current();old=json.loads((previous/'qualification-report.json').read_bytes());prior=json.loads((previous/'frozen.json').read_bytes());resume=json.loads((previous/'native-resume.json').read_bytes())
            assert old['status']=='failed-or-paused' and old['live_provider_calls']==8 and prior['previous_provider_calls']==22
            assert old['native']['slices'][-1]['admission_denied']=='qualification-budget'
            remaining=3600-int((dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(prior['aggregate_started_at'])).total_seconds());assert remaining>180
            with zipfile.ZipFile(previous/'qualification.zip') as z:
                resume['checkpoint']=old['native']['slices'][-1]['checkpoint'];resume['job']=json.loads(z.read('native-ledger.jsonl').splitlines()[-1])['job'];raw=z.read(next(n for n in z.namelist() if n.endswith('/checkpoint.zip') and '/'+resume['job']['id']+'/' in n));assert r.sha(raw)==resume['checkpoint']['sha256'];(out/'resume-checkpoint.zip').write_bytes(raw)
            resume['feedback']+=' The preceding qualification hit its separate development request allowance before completing. Continue the exact retained files and tool history; inspect/run the pending repair check, resolve any real command failures, and create the full candidate. Do not repeat completed setup, invent observations, or change the original fixture criteria.'
            save(out/'native-resume.json',resume);save(out/'followup.json',dict(previous_campaign=previous.name,previous_provider_calls=30,remaining_seconds=remaining,aggregate_started_at=prior['aggregate_started_at'],maximum_aggregate_calls=50,case_selection=[],reason='The declared thirty-request qualification stopped correctly and remains failed/paused. Separate predeclared development continuation allows at most twenty additional subscription calls under the original absolute one-hour limit to finish native repairs from retained files; no publication criterion, paper budget or evidence is changed.'))
            report['candidate']=freeze(out)
        elif args.mode=='repair-followup':
            previous=current();old=json.loads((previous/'qualification-report.json').read_bytes());prior=json.loads((previous/'frozen.json').read_bytes())
            assert old['status']=='failed-or-paused' and old['reason']=='ValueError: A package needs mode, package, arguments and parameters.'
            first=json.loads((BASE/prior['followup_of']/'qualification-report.json').read_bytes());calls=prior['previous_provider_calls']+old['live_provider_calls'];assert calls==22
            remaining=3600-int((dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(first['started_at'])).total_seconds());assert remaining>180
            with zipfile.ZipFile(previous/'qualification.zip') as z:
                receipt=json.loads(z.read('native-slice-2/receipt.json'));checkpoint=receipt['checkpoint'];job=json.loads(z.read('native-ledger.jsonl').splitlines()[-1])['job']
                compiled=json.loads(z.read(next(n for n in z.namelist() if n.endswith('candidate-compiled.json'))));raw=z.read(next(n for n in z.namelist() if n.endswith('/checkpoint.zip') and '/'+job['id']+'/' in n));assert r.sha(raw)==checkpoint['sha256']
                (out/'resume-checkpoint.zip').write_bytes(raw)
            save(out/'native-resume.json',dict(checkpoint=checkpoint,job=job,claim_id=compiled['protocol']['decision']['claim_id'],feedback='The candidate was rejected by actual network_spec validation: mode=loopback is invalid; the executable mode must be emulated or real-world. For this local loopback software control choose emulated, preserving the 127.0.0.1 parameters, hypothesis, complete decision and actual files. Inspect retained outputs; amend candidate.json, do not repeat completed setup.'))
            save(out/'followup.json',dict(previous_campaign=previous.name,previous_provider_calls=calls,remaining_seconds=remaining,aggregate_started_at=first['started_at'],case_selection=[],reason='Validate generated executable specs before candidate registration and continue the exact retained native project. Preserve the failed candidate and all 22 prior calls.'))
            report['candidate']=freeze(out)
        elif args.mode=='followup':
            previous=current();old=json.loads((previous/'qualification-report.json').read_bytes());archive=json.loads((previous/'archive-recovery.json').read_bytes())
            assert old['status']=='failed-or-paused' and old['live_provider_calls']==6 and archive['sha256']==archive['retrieved_sha256']
            remaining=3600-int((dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(old['started_at'])).total_seconds());assert remaining>180
            save(out/'followup.json',dict(previous_campaign=previous.name,previous_provider_calls=6,remaining_seconds=remaining,old_archive_sha256=archive['sha256'],reason='Increase the demonstrated total stream deadline with aligned dispatch fences; preserve the original unknown request. Repeat only the source-injection regression in the new timing configuration, then qualify the native file contract.'))
            report['candidate']=freeze(out)
        else:
            source=current();report['campaign']=source.name
            if args.mode=='prepare':report['command']=prepare(source)
            elif args.mode=='record-qualification':report['qualification']=record_qualification(source)
            elif args.mode=='migrate-window':report['migration']=migrate_window()
            elif args.mode=='verify-release':report['verification']=verify_release(source)
            elif args.mode=='verify-held':report['verification']=verify_held(source,out)
            elif args.mode=='observe-rerun':report['progress']=observe_rerun(source,out)
            elif args.mode=='record-release':report['release_record']=record_release(source,out)
            elif args.mode=='plan-rerun':report['rerun']=plan_rerun(source)
            elif args.mode in ('dry-run-rerun','create-rerun'):report['rerun']=create_rerun(source,dry_run=args.mode=='dry-run-rerun')
            elif args.mode=='diagnose':
                prep=json.loads((source/'prepare-command.json').read_bytes());host=prep['host']
                program="""import json,pathlib
p=pathlib.Path(HOST)
receipts=[]
for q in p.glob('answer-*/receipt.json'):
 d=json.loads(q.read_bytes());receipts.append(dict(case=q.parent.name,receipt={k:d.get(k) for k in ('status','error_code','http_status','response_received','wall_seconds','request_hash')},files=[dict(name=f.name,bytes=f.stat().st_size) for f in q.parent.iterdir() if f.is_file() and f.name!='config.json']))
large=sorted([dict(path=str(q.relative_to(p)),bytes=q.stat().st_size) for q in p.rglob('*') if q.is_file() and not q.is_symlink() and not any(n in ('state','node_modules') for n in q.relative_to(p).parts)],key=lambda r:r['bytes'],reverse=True)[:20]
print(json.dumps(dict(receipts=receipts,largest_files=large)))
""".replace('HOST',repr(host))
                report['command']=r.ssm(['/opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)]);save(source/'diagnose-command.json',report['command'])
            elif args.mode=='retain':
                prep=json.loads((source/'prepare-command.json').read_bytes());host=prep['host'];raw=(ROOT/'bin/retain_assessment_methods_qualification_host.py').read_bytes()
                install="from pathlib import Path;import base64;p=Path("+repr(host+'/retain-evidence.py')+");assert not p.exists();p.write_bytes(base64.b64decode("+repr(base64.b64encode(raw).decode())+"));p.chmod(0o644)"
                report['command']=r.ssm(['set -eu','python3.12 -c '+shlex.quote(install),'set -a','. /etc/jumpserve-openclaw.env','set +a','runuser -u jumpserve -- /opt/jumpserve/python/bin/python -B '+host+'/retain-evidence.py'])
                save(source/'retain-command.json',report['command'])
            elif args.mode=='retained':
                call=json.loads((source/'retain-command.json').read_bytes());value=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id'])
                if value['Status'] in ('Pending','InProgress','Delayed'):report.update(status='pending',command_status=value['Status']);return
                assert value['Status']=='Success',value.get('StandardErrorContent','')[-1000:]
                item=json.loads(value['StandardOutputContent']);raw=storage(item['path']);assert r.sha(raw)==item['sha256']==item['retrieved_sha256']
                (source/'qualification.zip').write_bytes(raw)
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    for entry in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(entry['path']))==entry['sha256']
                    save(source/'qualification-report.json',json.loads(z.read('report.json')))
                save(source/'archive-recovery.json',item);report['archive']=item
            elif args.mode=='start':
                assert not (source/'start-command.json').exists(),'Never replay a qualification dispatch.'
                prep=json.loads((source/'prepare-command.json').read_bytes());v=r.aws('ssm','get-command-invocation','--command-id',prep['command_id'],'--instance-id',prep['instance_id']);assert v['Status']=='Success'
                host=prep['host'];cmd='set -eu\nset -a\n. /etc/jumpserve-openclaw.env\nset +a\nrunuser -u jumpserve -- /opt/jumpserve/python/bin/python -B '+host+'/qualify.py > '+host+'/run.log 2>&1'
                packet=json.loads((source/'frozen.json').read_bytes());remaining=3600
                if packet.get('followup_of'):
                    prior=json.loads((BASE/packet['followup_of']/'qualification-report.json').read_bytes())
                    remaining=3600-int((dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(packet.get('aggregate_started_at') or prior['started_at'])).total_seconds())-10
                assert remaining>180,'Original aggregate qualification elapsed-time limit prevents another dispatch.'
                report['aggregate_remaining_seconds']=remaining
                report['command']=r.ssm(['systemd-run --unit=jumpserve-methods-'+source.name.lower()+' --property=RuntimeMaxSec='+str(remaining)+' /bin/bash -c '+shlex.quote(cmd)])
                save(source/'start-command.json',report['command'])
            elif args.mode=='status':
                prep=json.loads((source/'prepare-command.json').read_bytes());host=prep['host']
                program="import json,pathlib;p=pathlib.Path("+repr(host)+");v=json.loads((p/'report.json').read_bytes()) if (p/'report.json').exists() else {};print(json.dumps(dict(status=v.get('status'),calls=v.get('live_provider_calls'),cases=v.get('summaries',[]),archive=json.loads((p/'archive.json').read_bytes()) if (p/'archive.json').exists() else None,log_tail=(p/'run.log').read_text()[-1000:] if (p/'run.log').exists() else None)))"
                report['command']=r.ssm(['/opt/jumpserve/python/bin/python -B -c '+shlex.quote(program)]);save(source/'status-command.json',report['command'])
            else:
                call=json.loads((source/'status-command.json').read_bytes());value=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id']);assert value['Status']=='Success'
                state=json.loads(value['StandardOutputContent']);save(source/'remote-state.json',state)
                report['remote']=state
                if state.get('archive'):
                    item=state['archive'];raw=storage(item['path']);assert r.sha(raw)==item['sha256'];(source/'qualification.zip').write_bytes(raw)
                    with zipfile.ZipFile(io.BytesIO(raw)) as z:
                        for entry in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(entry['path']))==entry['sha256']
                        save(source/'qualification-report.json',json.loads(z.read('report.json')))
                    report['archive_verified']=True
        report['status']='complete'
    except Exception as error:report.update(status='failed',reason=str(error));raise
    finally:
        report['ended_at']=r.stamp();save(out/'receipt.json',report);print(json.dumps(dict(directory=str(out),**report),indent=2))

if __name__=='__main__':main()
