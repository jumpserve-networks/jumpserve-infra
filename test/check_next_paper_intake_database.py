"""Fixed local PostgreSQL regression. No remote transport or model calls."""
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy, paper_uploads, workflow
import autonomy_fixtures as fixture

ROOT = Path(__file__).resolve().parents[1]

def rpc(op, study, payload=None, actor=None):
    return json.loads(f.query("select public.research_paper_intake("+','.join([f.sql_text(op),f.sql_text(actor or f.ACTOR)+'::uuid',f.sql_text(study)+'::uuid',f.sql_json(payload or {})])+")",role='service_role'))

def main():
    f.bootstrap()
    # Exercise the actual category helper functions, without unrelated platform
    # supervisor migrations. Only their policy relation is synthesized here.
    f.query("create table public.autonomy_budget_categories(category text primary key,max_spend_cents integer,max_model_calls integer,revision integer);insert into public.autonomy_budget_categories values('research_assessment',-1,-1,1)")
    source=(ROOT/'database/202610310003_category_budgets.sql').read_text()
    for name in ['autonomy_assessment_budget_terms','autonomy_budget_allows']:
        start=source.index('create function public.'+name+'(')
        end=source.index('$$;',source.index('$$',start)+2)+3
        f.query(source[start:end])
    f.query((ROOT/'database/202611110001_next_paper_intake.sql').read_text())
    study=f.uid(); identity=dict(filename='original.pdf',sha256='a'*64,byte_count=100)
    row=rpc('reserve',study,identity)
    assert row['status']=='uploaded'
    assert rpc('reserve',study,identity)['source_id']==row['source_id']
    f.rejects(lambda:rpc('reserve',study,identity,actor=f.OTHER))
    for bad in [dict(identity,filename='../paper.pdf'),dict(identity,byte_count=0),dict(identity,sha256='bad')]:
        f.rejects(lambda:rpc('reserve',f.uid(),bad))
    payload=dict(model_id='gpt-5.4-mini-2026-03-17',reserved_cents=100,request=dict(model='gpt-5.4-mini-2026-03-17',input='retained source',background=True),paper_text=dict(totalPages=1,pages=[dict(page=1,text='Retained text')]),artifacts=[dict(id=row['original_artifact_id'],sha256='a'*64,byte_count=100,storage_path=study+'/'+'a'*64,media_type='application/pdf',provenance=dict(kind='paper-original-upload')),dict(id=row['text_artifact_id'],sha256='b'*64,byte_count=80,storage_path=study+'/'+'b'*64,media_type='application/json',provenance=dict(kind='paper-text-extraction'))])
    f.query("update public.autonomy_budget_categories set max_model_calls=0")
    f.rejects(lambda:rpc('begin',study,payload))
    assert rpc('reserve',study,identity)['model_calls']==0
    f.query("update public.autonomy_budget_categories set max_model_calls=-1")
    with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(lambda _:rpc('begin',study,payload),range(3)))
    assert sum(r['admitted'] for r in results)==1
    row=next(r for r in results if r['admitted']);token=row['submit_token']
    assert row['model_calls']==1 and row['reserved_cents']==100
    f.rejects(lambda:rpc('submitted',study,dict(token=f.uid(),response_id='resp_test',response={})))
    row=rpc('submitted',study,dict(token=token,response_id='resp_test',response=dict(status='queued')))
    assert rpc('submitted',study,dict(token=token,response_id='resp_test'))['revision']==row['revision']
    f.rejects(lambda:rpc('submitted',study,dict(token=token,response_id='resp_other')))
    f.rejects(lambda:rpc('finish',study,dict(response_id='resp_test')))
    breakdown=dict(status='ready',source_id=row['source_id'],text_artifact_id=row['text_artifact_id'])
    row=rpc('finish',study,dict(response_id='resp_test',response=dict(status='completed'),breakdown=breakdown,title='Retained title',domain='Networking',authors=['Test Author']))
    assert row['status']=='ready' and rpc('begin',study,payload)['admitted'] is False
    assert f.query("select status from research_paper_reviews where study_id="+f.sql_text(study))=='ready'
    assert f.query("select count(*) from research_paper_intake_events where study_id="+f.sql_text(study))=='4'
    for table in ['research_autonomy_workflows','research_autonomy_tasks','research_model_dispatches','research_queue_jobs']:
        assert f.query('select count(*) from '+table+" where study_id="+f.sql_text(study))=='0',table
    for role in ['anon','authenticated']:
        assert f.query("select has_function_privilege(current_user,'research_paper_intake(text,uuid,uuid,jsonb)','EXECUTE')",role=role)=='f'
        for table in ['research_paper_intakes','research_paper_intake_events']:
            f.rejects(lambda:f.query('select * from '+table,role=role))
    f.rejects(lambda:f.query('delete from research_paper_intake_events'))
    # A cancelled original is never admitted after retry.
    other=f.uid();rpc('reserve',other,identity);assert rpc('cancel',other)['status']=='cancelled'
    assert rpc('begin',other,payload)['admitted'] is False
    # Resume an actual legacy queued upload without resetting its deadline or
    # commitments. Running intake leases must remain on their original path.
    f.rpc('publish_agent_prompt',fixture.publish_fixture())
    os.environ['RESEARCH_AUTONOMY_ENABLED']='true'
    def legacy():
        original=fixture.pdf_bytes();legacy_id=f.uid()
        metadata=dict(filename='legacy.pdf',sha256=workflow.digest(original),byte_count=len(original))
        with patch.object(autonomy,'wake',return_value=dict(status='deferred')):
            paper_uploads.submit(f.ACTOR,dict(action='reserve',request_id=legacy_id,**metadata))
            f.transport('/storage/v1/object/'+paper_uploads.BUCKET+'/'+legacy_id+'/'+metadata['sha256'],'POST',original)
            paper_uploads.submit(f.ACTOR,dict(action='prepare',request_id=legacy_id))
        return legacy_id,metadata
    legacy_id,metadata=legacy()
    before=json.loads(f.query('select to_jsonb(w) from research_autonomy_workflows w where study_id='+f.sql_text(legacy_id)))
    adopted=rpc('reserve',legacy_id,metadata)
    after=json.loads(f.query('select to_jsonb(w) from research_autonomy_workflows w where study_id='+f.sql_text(legacy_id)))
    assert after['status']=='cancelled' and after['committed_cents']==before['committed_cents']
    assert adopted['deadline_at']==before['deadline_at']
    active_id,metadata=legacy()
    task=f.rpc('research_autonomy_control',dict(p_operation='lease',p_actor=None,p_study=None,p_payload={}))
    assert task['study_id']==active_id
    f.rejects(lambda:rpc('reserve',active_id,metadata))
    assert f.query('select count(*) from research_paper_intakes where study_id='+f.sql_text(active_id))=='0'
    print(json.dumps(dict(database=f.DATABASE,passed=True,checks=['one admission under concurrency','category zero stops inference','immutable provider identity and history','private owner gate','no workers or experiment jobs','cancel is terminal'])))

if __name__=='__main__':main()
