"""Real local Postgres capture/backfill plus authenticated catalogue projection.

Synthetic paper text; no browser, provider request or production mutation.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import check_research_ideas_database as f
import prompt_catalog


def main():
    f.bootstrap()
    q=f.sql_text;j=f.sql_json
    f.query((f.ROOT/'database/202611110001_next_paper_intake.sql').read_text())
    front=f.ROOT.parent/'jumpserve-front-end'
    source="import {paperModelRequest} from './lib/paper-intake-model.ts';console.log(JSON.stringify(paperModelRequest({totalPages:1,pages:[{page:1,text:'PRIVATE_PAPER_A_731'}]})));"
    result=subprocess.run(['node','--import','./scripts/lib/register-typescript.mjs','--input-type=module','-e',source],cwd=front,text=True,capture_output=True,check=True,timeout=10)
    request=json.loads(result.stdout)

    def js(sql,role=None):return json.loads(f.query(sql,role=role) or 'null')
    def reserve():
        study=f.uid();upload=dict(filename='Synthetic prompt fixture.pdf',sha256='a'*64,byte_count=100)
        f.query("select public.research_paper_intake('reserve',"+q(f.ACTOR)+"::uuid,"+q(study)+"::uuid,"+j(upload)+")",role='service_role')
        return study
    def admit(study,body,status='submitting'):
        # Exercise the actual intake history/capture triggers without calling a
        # model. Production's begin RPC performs this update in its admission TX.
        f.query('update research_paper_intakes set request='+j(body)+',model_calls=1,status='+q(status)+' where study_id='+q(study))
    def use(study):return js('select to_jsonb(u) from research_paper_prompt_uses u where study_id='+q(study))

    historical=reserve();admit(historical,request,'cancelled')
    original=f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(historical))
    events=f.query('select jsonb_agg(to_jsonb(e) order by revision) from research_paper_intake_events e where study_id='+q(historical))
    f.query((f.ROOT/'database/202611110003_paper_prompt_catalog.sql').read_text())

    def backfill():
        assert use(historical)['prompt_version_id']
        assert f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(historical))==original
        assert f.query('select jsonb_agg(to_jsonb(e) order by revision) from research_paper_intake_events e where study_id='+q(historical))==events
        expected=f.query("select min(created_at) from research_paper_intake_events where study_id="+q(historical)+" and snapshot->'request'="+j(request))
        assert f.query('select created_at from research_paper_prompt_versions where id='+q(use(historical)['prompt_version_id']))==expected
    f.check('historical exact prompts are linked without changing terminal evidence or timestamps',backfill)

    def concurrent():
        second=reserve();third=reserve();different_paper=dict(request,input=request['input'].replace('PRIVATE_PAPER_A_731','PRIVATE_PAPER_B_731'))
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda study:admit(study,different_paper),[second,third]))
        assert use(second)['prompt_version_id']==use(third)['prompt_version_id']==use(historical)['prompt_version_id']
        assert use(second)['request_sha256']==use(third)['request_sha256']!=use(historical)['request_sha256']
        assert f.query('select count(*) from research_paper_prompt_versions')=='1'
        changed=reserve();admit(changed,dict(request,instructions=request['instructions']+'\nExplicit synthetic candidate.'))
        schema_changed=reserve();configuration=json.loads(json.dumps(request));configuration['max_output_tokens']+=1;admit(schema_changed,configuration)
        assert len({use(study)['prompt_version_id'] for study in [historical,changed,schema_changed]})==3
    f.check('atomic admission links exact requests; duplicate templates share a version and changes create versions',concurrent)

    def invalid_and_private():
        study=reserve();before=f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study))
        count=f.query('select count(*) from research_paper_prompt_versions')
        for body in [dict(request,metadata={'email':'PRIVATE_ACCOUNT_731'}),dict(request,instructions=''),dict(request,input='[]')]:
            f.rejects(lambda:admit(study,body));assert use(study) is None
            assert f.query('select to_jsonb(i) from research_paper_intakes i where study_id='+q(study))==before
        assert f.query('select count(*) from research_paper_prompt_versions')==count
        for role in ('anon','authenticated'):
            for table in ('research_paper_prompt_versions','research_paper_prompt_uses'):f.rejects(lambda:f.query('select * from '+table,role=role))
        for role in ('anon','authenticated','service_role'):
            assert f.query("select has_function_privilege(current_user,'public.research_record_paper_prompt(uuid,jsonb,timestamptz)','EXECUTE')",role=role)=='f'
        f.rejects(lambda:f.query("update research_paper_prompt_versions set instructions='Changed'"))
        f.rejects(lambda:f.query('delete from research_paper_prompt_uses'))
    f.check('invalid capture rolls back admission and browser writes or evidence edits stay denied',invalid_and_private)

    def catalogue():
        allowed={'agent_prompt_versions','agent_prompt_settings','research_paper_prompt_versions'}
        def read(table,params):
            assert table in allowed
            columns=params['select'].split(',');assert all(column.replace('_','').isalnum() for column in columns)
            where=' where id='+q(params['id'][3:])+'::uuid' if params.get('id') else ''
            order=' order by '+params['order'].replace('.asc','') if params.get('order') else ''
            return js("select coalesce(jsonb_agg(to_jsonb(t)),'[]') from (select "+','.join(columns)+' from '+table+where+order+' offset '+str(int(params.get('offset',0)))+' limit '+str(min(2,int(params['limit'])))+')t',role='service_role')
        with patch.object(prompt_catalog,'read',side_effect=read):
            catalog=prompt_catalog.index();papers=[item for item in catalog['prompts'] if item.get('recorded')]
            assert len(papers)==3
            values=[prompt_catalog.detail(item['id'])['prompt'] for item in papers]
            serialized=json.dumps([catalog,values]);assert 'PRIVATE_PAPER_A_731' not in serialized and 'PRIVATE_PAPER_B_731' not in serialized
            item=prompt_catalog.detail(use(historical)['prompt_version_id'])['prompt']
            assert item['system_prompt']==request['instructions']
            configuration=json.loads(item['research_context']);assert configuration['request_configuration']=={k:v for k,v in request.items() if k not in ('input','instructions')}
            assert item['active'] is False and item['published_at'] is None
    f.check('actual catalogue lists registered templates and complete model/schema settings without private source text',catalogue)
    print(json.dumps(dict(passed=True,checks=f.report['checks'],database=f.DATABASE)))


if __name__=='__main__':main()
