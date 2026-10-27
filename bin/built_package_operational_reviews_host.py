"""Two real, fresh, read-only operational plan reviews using the existing grant.

This structured review transport does not claim native command execution. Native
builder execution has its own separately bounded qualification campaign.
"""
import datetime as dt,io,json,pathlib,sys,time,uuid
sys.path.insert(0,'/opt/jumpserve/runtime')
import store,openclaw_runtime as runtime,siwc_protocol as wire
from workflow import canonical,digest
base=pathlib.Path(sys.argv[1]);job=json.loads((base/'request.json').read_bytes());study=job['study'];actor=job['actor'];packet=job['packet']
settings=store.request('/rest/v1/agent_prompt_settings?module_id=eq.research-verification&select=active_version_id')[0]
prompt=store.request('/rest/v1/agent_prompt_versions?id=eq.'+settings['active_version_id']+'&select=id,system_prompt,research_context,published_at')[0]
assert prompt['published_at']
schema=dict(type='object',properties=dict(summary={'type':'string'},questions=dict(type='array',items={'type':'string'}),findings=dict(type='array',items=dict(type='object',properties=dict(severity=dict(type='string',enum=['warning','blocking']),field={'type':'string'},message={'type':'string'}),required=['severity','field','message'],additionalProperties=False)),verdict=dict(type='string',enum=['ready','needs-clarification'])),required=['summary','questions','findings','verdict'],additionalProperties=False)
results=[]
for task in ('comprehension','critic'):
    identity=str(uuid.uuid4());provenance=dict(packet_sha256=packet['sha256'],context_policy='fresh-packet-only',history_messages=0,evaluator=dict(identity='gpt-6.1-sol via legitimate ChatGPT grant',type='AI',independent=False),runtime='subscription-structured-review-v1',reserved_cents=100,measured_charges_usd=None)
    logical=dict(modelId=runtime.MODEL,system=[dict(text=prompt['system_prompt']),dict(text=prompt['research_context'])],messages=[dict(role='user',content=[dict(text=canonical(dict(task=task,packet=packet['document'],scope='Fixed private software deployment control, not a research hypothesis or published claim.')).decode())])],toolConfig=dict(tools=[dict(toolSpec=dict(name='submit_idea_review',description='Submit the read-only plan review.',inputSchema=dict(json=schema)))]))
    payload=dict(p_study=study,p_actor=actor,p_id=identity,p_packet=packet['id'],p_task=task,p_session=None,p_user='service-operational-release',p_prompt=prompt['id'],p_model=runtime.MODEL,p_request=logical,p_provenance=provenance)
    raw=canonical(wire.response_request(logical));(base/(task+'-request.json')).write_bytes(raw);status='failed';reason='Unknown provider outcome';parsed=None;completed=None
    store.request('/rest/v1/rpc/research_begin_idea_run','POST',payload)
    try:
        token=runtime.credential()
        with runtime.http_request('POST','https://api.openai.com/v1/responses',token,raw) as response:
            with (base/(task+'-response.bin')).open('wb') as sink:
                if response.status!=200:sink.write(response.read(1000000));raise RuntimeError('Provider returned HTTP '+str(response.status))
                completed=wire.read_stream(response,sink,time.monotonic()+65,1000000)
        assert completed['model']==runtime.MODEL
        texts=[c['text'] for item in completed.get('output',[]) if item.get('type')=='message' for c in item.get('content',[]) if c.get('type')=='output_text']
        assert len(texts)==1
        parsed=json.loads(texts[0])
        assert set(parsed)=={'summary','questions','findings','verdict'}
        assert parsed['verdict']!='ready' or not parsed['questions'] and not any(f['severity']=='blocking' for f in parsed['findings'])
        status='complete';reason=None
    finally:
        original=(base/(task+'-response.bin')).read_bytes() if (base/(task+'-response.bin')).exists() else b''
        # Retain exact SSE separately; the run keeps its exact parsed response JSON.
        key='release-verification/built-package-reviews/'+identity+'/'+digest(original)+'.sse';url='/storage/v1/object/research-workflow-raw/'+key
        store.request(url,'POST',original);assert digest(store.request(url,raw=True))==digest(original)
        provenance.update(raw_response_scope=dict(provider_archive=dict(bucket='research-workflow-raw',path=key,sha256=digest(original),retrieved_sha256=digest(original)),actual_answer_reviewed=False))
        output_raw=texts[0] if parsed else None
        store.request('/rest/v1/rpc/research_finish_idea_run','POST',dict(p_study=study,p_actor=actor,p_id=identity,p_status=status,p_reason=reason,p_raw=output_raw,p_output=parsed,p_usage=wire.usage(completed) if completed else None,p_provenance=provenance,p_messages=None))
    results.append(dict(task=task,id=identity,output=parsed,provenance=provenance))
    (base/'report.json').write_bytes(canonical(dict(results=results)))
    if status!='complete' or parsed['verdict']!='ready':raise RuntimeError('Actual operational review did not pass; preserve it.')
print(json.dumps(dict(results=results)),flush=True)
