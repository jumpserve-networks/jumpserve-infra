"""New quality gates against the existing isolated native Postgres chain.
No Docker, remote DB writes, provider inference or generated experiment execution.
"""
import json
import copy
import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor
import subprocess
import check_shared_experiment_scripts_database as previous
import check_research_ideas_database as f


def main():
    cache=f.ROOT/'.test-artifacts/paper-quality-base.json'
    fingerprint=hashlib.sha256(b''.join(p.name.encode()+p.read_bytes() for p in sorted((f.ROOT/'database').glob('*.sql')) if p.name<'202611180001_paper_quality_reviews.sql')).hexdigest()
    if '--reuse-base' in sys.argv and cache.exists():
        saved=json.loads(cache.read_text())
        assert saved['fingerprint']==fingerprint and saved['database'].startswith('jumpserve_research_ideas_test_')
        f.query('create database '+f.DATABASE+' template '+saved['database'],database='postgres')
        f.ACTOR=saved['actor'];f.OTHER=saved['other']
    else:
        previous.main()
        base=f.DATABASE+'_quality_base'
        f.query('create database '+base+' template '+f.DATABASE,database='postgres')
        cache.write_text(json.dumps(dict(fingerprint=fingerprint,database=base,actor=f.ACTOR,other=f.OTHER)))
    tables = ['research_paper_intakes', 'research_experiment_plans', 'research_experiment_scripts']
    before = {t: f.query("select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,'[]')) from " + t + ' t') for t in tables}
    migration = (f.ROOT / 'database/202611180001_paper_quality_reviews.sql').read_text()
    f.query(migration)
    f.query(migration)
    assert before == {t: f.query("select md5(coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,'[]')) from " + t + ' t') for t in tables}
    assert f.query('select count(*) from research_paper_quality_workflows') == '0'
    for table in ['research_paper_quality_workflows', 'research_paper_quality_calls', 'research_paper_quality_events', 'research_paper_quality_prompt_uses']:
        for role in ['anon', 'authenticated']:
            f.rejects(lambda role=role, table=table: f.query('select * from '+table, role=role))
        for role in ['anon', 'authenticated', 'service_role']:
            f.rejects(lambda role=role, table=table: f.query('delete from '+table, role=role))
    q = f.sql_text
    front = f.ROOT.parent / 'jumpserve-front-end'
    def fixture(payload):
        return json.loads(subprocess.run(['node','--import','./scripts/lib/register-typescript.mjs','tests/support/paper-quality-database.mjs'],cwd=front,input=json.dumps(payload),capture_output=True,text=True,check=True).stdout)
    def quality(w, op, payload=None, actor=None, role='service_role'):
        return json.loads(f.query('select research_paper_quality_control('+q(op)+','+q(actor or f.ACTOR)+'::uuid,'+q(w['id'])+'::uuid,'+f.sql_json(payload or {})+')',role=role))
    study=f.uid()
    i=json.loads(f.query('select research_paper_intake(\'reserve\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(dict(filename='Quality gate fixture.pdf',sha256='b'*64,byte_count=100))+')',role='service_role'))
    data=fixture(dict(mode='initial',study=study,source_id=i['source_id'],text_artifact_id=i['text_artifact_id']))
    response=data['intake_response'];response['id']='resp_original_quality_'+study.replace('-','')
    f.query('update research_paper_intakes set status=\'ready\',request='+f.sql_json(data['intake_request'])+',paper_text='+f.sql_json(data['paper'])+',breakdown='+f.sql_json(data['breakdown'])+',provider_response_id='+q(response['id'])+',response='+f.sql_json(response)+',reserved_cents=100,model_calls=1 where study_id='+q(study))
    original={t:f.query('select to_jsonb(t) from '+t+' t where study_id='+q(study)) for t in ['research_paper_intakes']}
    w=json.loads(f.query('select research_quality_result(id) from research_paper_quality_workflows where study_id='+q(study)+' and step=2'))
    assert w['status']=='review_pending'
    blocked=dict(intake_revision=int(f.query('select revision from research_paper_intakes where study_id='+q(study))),confirmed_breakdown=data['breakdown'],request=data['plan_request'])
    f.rejects(lambda:f.query('select research_experiment_plan(\'confirm\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(blocked)+')',role='service_role'))
    calls=0
    def finish_review(w, revise=False):
        nonlocal calls
        pending=fixture(dict(mode='review',workflow=w,response_id='resp_quality_'+str(calls+1)+'_'+study.replace('-',''),revise=revise))
        admitted=quality(w,'admit',dict(source_sha256=pending['source_sha256']))
        assert admitted['admitted'] is True
        assert quality(w,'admit',dict(source_sha256=pending['source_sha256']))['admitted'] is False
        c=admitted['call'];identity=dict(call_id=c['id'],token=c['submit_token'])
        f.rejects(lambda:quality(w,'request',dict(identity,request={**pending['request'],'reasoning':{'effort':'low'}})))
        ready=quality(w,'request',dict(identity,request=pending['request']))
        assert ready['call']['request']['reasoning']['effort']=='high'
        submitted=quality(w,'submitted',dict(identity,response_id=pending['response']['id'],response={'id':pending['response']['id'],'status':'queued'}))
        f.rejects(lambda:quality(w,'reviewed',dict(identity,response={**pending['response'],'id':'resp_wrong'},review=pending['review'],checks=pending['checks'])))
        if w['step']==4:
            fake=copy.deepcopy(pending);fake['response']['output'][0]['code']='print(\'forged pass\')'
            f.rejects(lambda:quality(w,'reviewed',dict(identity,response=fake['response'],review=fake['review'],checks=fake['checks'])))
            # Some provider responses omit logs. The exact completed checker
            # must still exist; retain the original container file separately.
            content=json.dumps(pending['checks']['sandbox']['result'],sort_keys=True)
            pending['checks']['sandbox']['artifact']=dict(file_id='cfile_fixture',path='/mnt/data/jumpserve-quality-'+pending['source_sha256']+'-result.json',content=content,content_sha256=hashlib.sha256(content.encode()).hexdigest())
            pending['response']['output'][0]['outputs']=[]
            code=pending['response']['output'][0]['code']
            pending['response']['output'][0]['code']="checker = r'''\n"+code+"\n'''\nns = {}\nexec(checker, ns, ns)"
            fake=copy.deepcopy(pending);fake['checks']['sandbox']['artifact']['content_sha256']='0'*64
            f.rejects(lambda:quality(w,'reviewed',dict(identity,response=fake['response'],review=fake['review'],checks=fake['checks'])))
        calls+=1
        payload=dict(identity,response=pending['response'],review=pending['review'],checks=pending['checks'])
        result=quality(w,'reviewed',payload)
        assert quality(w,'reviewed',payload)['status']==result['status']
        return result
    def repair(w):
        nonlocal calls
        pending=fixture(dict(mode='repair',workflow=w,response_id='resp_quality_'+str(calls+1)+'_'+study.replace('-','')))
        admitted=quality(w,'admit',dict(source_sha256=pending['source_sha256']));assert admitted['call']['kind']=='repair'
        identity=dict(call_id=admitted['call']['id'],token=admitted['call']['submit_token'])
        ready=quality(w,'request',dict(identity,request=pending['request']));assert ready['call']['request']['reasoning']['effort']=='medium'
        quality(w,'submitted',dict(identity,response_id=pending['response']['id'],response={'id':pending['response']['id'],'status':'queued'}))
        calls+=1
        return quality(w,'repaired',dict(identity,response=pending['response'],candidate=pending['candidate'],checks=pending['checks']))
    for role in ['anon','authenticated']:
        f.rejects(lambda role=role:quality(w,'admit',dict(source_sha256='a'*64),role=role))
    f.rejects(lambda:quality(w,'admit',dict(source_sha256='a'*64),actor=f.OTHER))
    w=finish_review(w,True);assert w['status']=='repair_pending'
    w=repair(w);assert w['status']=='review_pending' and w['round']==1
    w=finish_review(w);assert w['status']=='approved'
    assert f.query('select to_jsonb(t) from research_paper_intakes t where study_id='+q(study))==original['research_paper_intakes']
    approved_breakdown=w['candidate']['breakdown']
    data=fixture(dict(mode='initial',study=study,source_id=i['source_id'],text_artifact_id=i['text_artifact_id'],breakdown=approved_breakdown))
    payload=dict(intake_revision=blocked['intake_revision'],confirmed_breakdown=approved_breakdown,request=data['plan_request'])
    plan=json.loads(f.query('select research_experiment_plan(\'confirm\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(payload)+')',role='service_role'))
    plan_response={'id':'resp_plan_quality_'+study.replace('-',''),'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(data['plan'])}]}]}
    f.query('select research_experiment_plan(\'submitted\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(dict(token=plan['submit_token'],response_id=plan_response['id'],response={'id':plan_response['id'],'status':'queued'}))+')',role='service_role')
    f.query('select research_experiment_plan(\'finish\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,'+f.sql_json(dict(token=plan['submit_token'],response_id=plan_response['id'],response=plan_response,plan=data['plan']))+')',role='service_role')
    raw_plan=f.query('select to_jsonb(t) from research_experiment_plans t where study_id='+q(study))
    f.rejects(lambda:f.query('select research_experiment_scripts_control(\'generate\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,1,'+f.sql_json(dict(request=data['scripts_request']))+')',role='service_role'))
    w=json.loads(f.query('select research_quality_result(id) from research_paper_quality_workflows where study_id='+q(study)+' and step=3'))
    w=finish_review(w,True);w=repair(w);w=finish_review(w);assert w['status']=='approved'
    assert raw_plan==f.query('select to_jsonb(t) from research_experiment_plans t where study_id='+q(study))
    data=fixture(dict(mode='initial',study=study,source_id=i['source_id'],text_artifact_id=i['text_artifact_id'],breakdown=approved_breakdown,plan=w['candidate']))
    script=json.loads(f.query('select research_experiment_scripts_control(\'generate\','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,1,'+f.sql_json(dict(request=data['scripts_request']))+')',role='service_role'))
    script_response={'id':'resp_scripts_quality_'+study.replace('-',''),'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(data['scripts'])}]}]}
    for op,payload in [('submitted',dict(token=script['submit_token'],response_id=script_response['id'],response={'id':script_response['id'],'status':'queued'})),('finish',dict(token=script['submit_token'],response_id=script_response['id'],response=script_response,command_set=data['scripts']))]:
        f.query('select research_experiment_scripts_control('+q(op)+','+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid,1,'+f.sql_json(payload)+')',role='service_role')
    raw_scripts=f.query('select to_jsonb(t) from research_experiment_scripts t where study_id='+q(study))
    w=json.loads(f.query('select research_quality_result(id) from research_paper_quality_workflows where study_id='+q(study)+' and step=4'))
    f.rejects(lambda:f.query('select research_delete_assessment('+q(f.ACTOR)+'::uuid,'+q(study)+'::uuid)',role='service_role'))
    w=finish_review(w,True);w=repair(w);w=finish_review(w);assert w['status']=='approved'
    assert raw_scripts==f.query('select to_jsonb(t) from research_experiment_scripts t where study_id='+q(study))
    assert f.query('select count(*) from research_paper_quality_calls where study_id='+q(study))=='9'
    catalog=f.query('select jsonb_agg(to_jsonb(p)) from research_paper_prompt_versions p join research_paper_quality_prompt_uses u on u.prompt_version_id=p.id where u.study_id='+q(study))
    assert study not in catalog and 'file-fixture' not in catalog and 'Source and implementation checks passed.' not in catalog
    f.rejects(lambda:f.query('update research_paper_quality_workflows set candidate=\'{}\' where id='+q(w['id'])))
    f.rejects(lambda:f.query('update research_paper_quality_calls set provider_response_id=\'resp_replaced\' where workflow_id='+q(w['id'])))
    f.rejects(lambda:f.query('delete from research_paper_quality_events where study_id='+q(study)))
    # Reuse the real reservation/capture path for independent failure cases.
    def fresh():
        sid=f.uid();i=json.loads(f.query('select research_paper_intake(\'reserve\','+q(f.ACTOR)+'::uuid,'+q(sid)+'::uuid,'+f.sql_json(dict(filename='Quality '+sid+'.pdf',sha256=hashlib.sha256(sid.encode()).hexdigest(),byte_count=100))+')',role='service_role'))
        d=fixture(dict(mode='initial',study=sid,source_id=i['source_id'],text_artifact_id=i['text_artifact_id']))
        resp=d['intake_response'];resp['id']='resp_original_'+sid.replace('-','')
        f.query('update research_paper_intakes set status=\'ready\',request='+f.sql_json(d['intake_request'])+',paper_text='+f.sql_json(d['paper'])+',breakdown='+f.sql_json(d['breakdown'])+',provider_response_id='+q(resp['id'])+',response='+f.sql_json(resp)+',reserved_cents=100,model_calls=1 where study_id='+q(sid))
        return json.loads(f.query('select research_quality_result(id) from research_paper_quality_workflows where study_id='+q(sid)))
    w=fresh();pending=fixture(dict(mode='review',workflow=w,response_id='resp_concurrent_quality'))
    with ThreadPoolExecutor(max_workers=3) as pool:
        admissions=list(pool.map(lambda _:quality(w,'admit',dict(source_sha256=pending['source_sha256'])),range(3)))
    assert sum(a['admitted'] for a in admissions)==1
    admitted=next(a for a in admissions if a['admitted']);identity=dict(call_id=admitted['call']['id'],token=admitted['call']['submit_token'])
    quality(w,'request',dict(identity,request=pending['request']))
    lost=quality(w,'uncertain',dict(identity,reason='Lost provider acknowledgement'))
    assert lost['status']=='uncertain' and quality(w,'admit',dict(source_sha256=pending['source_sha256']))['admitted'] is False
    f.rejects(lambda:quality(w,'cancel',dict(identity,reason='Cannot invent cancellation')))
    f.rejects(lambda:f.query('select research_delete_assessment('+q(f.ACTOR)+'::uuid,'+q(w['study_id'])+'::uuid)',role='service_role'))
    quality(w,'submitted',dict(identity,response_id='resp_concurrent_quality',response={'id':'resp_concurrent_quality','status':'queued'}))
    f.rejects(lambda:quality(w,'cancel',dict(identity,response={'id':'resp_other','status':'cancelled'})))
    stopped=quality(w,'cancel',dict(identity,response={'id':'resp_concurrent_quality','status':'cancelled'},reason='Confirmed provider cancellation'));assert stopped['status']=='cancelled'
    f.query('select research_delete_assessment('+q(f.ACTOR)+'::uuid,'+q(w['study_id'])+'::uuid)',role='service_role')
    w=fresh();w=finish_review(w,True);w=repair(w);w=finish_review(w,True);assert w['status']=='needs_attention'
    assert quality(w,'admit',dict(source_sha256='0'*64))['admitted'] is False
    assert f.query('select count(*) from research_paper_quality_calls where workflow_id='+q(w['id']))=='3'
    w=fresh();pending=fixture(dict(mode='review',workflow=w,response_id='resp_budget_quality'))
    unspecified=copy.deepcopy(w['candidate']);unspecified['breakdown']['provenance']=dict(classification='unspecified',statement=None,citations=[])
    assert f.query('select research_valid_quality_candidate(w,'+f.sql_json(unspecified)+') from research_paper_quality_workflows w where id='+q(w['id']))=='t'
    policies=f.query('select jsonb_agg(to_jsonb(t)) from autonomy_budget_categories t')
    f.query('update autonomy_budget_categories set max_model_calls=1')
    f.rejects(lambda:quality(w,'admit',dict(source_sha256=pending['source_sha256'])))
    f.query('update autonomy_budget_categories set max_model_calls=2')
    admitted=quality(w,'admit',dict(source_sha256=pending['source_sha256']));assert admitted['admitted'] is True
    f.rejects(lambda:f.query('select research_assert_quality_budget('+q(w['study_id'])+'::uuid,100,1)'))
    for policy in json.loads(policies):
        f.query('update autonomy_budget_categories set max_model_calls='+str(policy['max_model_calls'])+' where category='+q(policy['category']))
    print(json.dumps(dict(passed=True,database=f.DATABASE,quality_calls=calls,checks=['idempotent migration and untouched history','owner-only/RLS/RPC-only writes','draft approval gates enforced by SQL','high reviews and medium one-time repairs for all stages','original response/source/check binding','fake sandbox log/artifact rejection','private generic prompt catalogue','concurrent single admission and duplicate reconciliation','uncertain identity retained without replay','confirmed cancellation and deletion guard','one repair limit and aggregate original budgets','immutable versioned evidence'])))


if __name__ == '__main__':
    main()
