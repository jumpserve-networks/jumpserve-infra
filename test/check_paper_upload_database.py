"""Actual local SQL/PDF upload path; synthetic Google, Storage and notifications."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import check_research_ideas_database as f
import autonomy, autonomy_sources as sources, paper_uploads, store, workflow


def main():
 f.report.update(protocol='private-paper-upload-v1',design='Exposed software tests; actual Postgres RPCs, API orchestration and PDF parser. Google authentication, Storage transport and wake notifications are fixtures.',
     conditional_gaps=['Legitimate Google-authenticated browser request','Remote signed Supabase Storage upload/CORS and bucket enforcement','Production migrations/deployment'],new_model_calls=0,new_cloud_experiments=0)
 try:
  f.bootstrap()
  layer=f.ROOT/'.runtime-autonomy-python/python';sys.path.insert(0,str(layer))
  from pypdf import PdfWriter
  from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
  writer=PdfWriter();page=writer.add_blank_page(width=400,height=400);stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 40 200 Td (Uploaded software fixture: latency is 10 ms.) Tj ET')
  font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
  page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})});page[NameObject('/Contents')]=writer._add_object(stream)
  buffer=io.BytesIO();writer.write(buffer);raw=buffer.getvalue()
  def body(data=raw,**changes):return dict(dict(action='reserve',request_id=f.uid(),filename='Previously assessed paper.pdf',sha256=workflow.digest(data),byte_count=len(data),domain='Software verification',scope='Synthetic input only; no academic assessment.'),**changes)
  def stage(request,data):
   path='/storage/v1/object/'+paper_uploads.BUCKET+'/'+request['request_id']+'/'+request['sha256']
   f.transport(path,'POST',data)
  request=body();study=request['request_id']
  with patch.object(autonomy,'wake',return_value=dict(status='deferred',reason='Explicit local notification fixture')):
   def reservation():
    first=paper_uploads.submit(f.ACTOR,request);assert first==paper_uploads.submit(f.ACTOR,request)
    assert f.query('select count(*) from research_studies where id='+f.sql_text(study))=='0'
    assert f.query('select count(*) from research_autonomy_workflows')=='0'
    f.rejects(lambda:paper_uploads.submit(f.OTHER,request))
    f.rejects(lambda:paper_uploads.submit(f.ACTOR,dict(request,sha256='0'*64)))
    return dict(exact_hash=first['sha256'],pending_without_workflow=True,same_id_replay=True,wrong_owner_denied=True)
   f.check('owner-scoped reservation is immutable and does not start work before upload',reservation)
   def interrupted():
    f.rejects(lambda:paper_uploads.submit(f.ACTOR,dict(action='start',request_id=study)))
    assert f.query('select status from research_paper_uploads where id='+f.sql_text(study))=='pending'
    assert f.query('select count(*) from research_autonomy_workflows')=='0'
    return dict(missing_original_not_zero_or_success=True,original_request_retained=True)
   f.check('missing upload remains retryable without a study or model request',interrupted)
   stage(request,raw)
   def finalization():
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:paper_uploads.submit(f.ACTOR,dict(action='start',request_id=study)),range(3)))
    assert all(r['id']==study for r in results)
    assert f.query('select count(*) from research_autonomy_workflows where study_id='+f.sql_text(study))=='1'
    assert f.query('select count(*) from research_autonomy_tasks where study_id='+f.sql_text(study))=='1'
    s=autonomy.one('studies',study,study);assert s['paper_url'] is None and s['paper_upload']['sha256']==workflow.digest(raw)
    w=store.rows('autonomy_workflows',dict(study_id='eq.'+study))[0];initial=json.loads(w['initial_prompt']);assert initial['paper']['paper_upload']['sha256']==workflow.digest(raw) and w['max_attempts']==25 and w['max_spend_cents']==10000
    replay=paper_uploads.submit(f.ACTOR,request);assert replay['status']=='started' and replay['result']['id']==study
    return dict(concurrent_completions=3,workflows=1,intake_tasks=1,initial_prompt_sha256=w['initial_sha256'],paper_url=None,original_hash_verified=True)
   f.check('three concurrent completions atomically retain bytes and create only one workflow',finalization)
   def parser():
    s=autonomy.one('studies',study,study)
    # Lambda adds its layer to the parent sys.path, not necessarily PYTHONPATH.
    # Exercise that distinction with the real pinned parser subprocess.
    with patch.object(sources,'fetch',side_effect=AssertionError('Uploaded PDF must never be fetched from the Internet')),patch.dict(os.environ):
     os.environ.pop('PYTHONPATH',None)
     result=sources.original(s,f.ACTOR)
    packet=json.loads(store.artifact_bytes(study,result['text_artifact_id'],maximum=1000000));source=autonomy.one('sources',study,result['source_id'])
    assert packet['original_sha256']==workflow.digest(raw) and 'latency is 10 ms' in packet['pages'][0]['text']
    assert source['source_url'] is None and source['retrieved_url'] is None and source['review_status']=='retrieved-unreviewed'
    assert store.artifact_bytes(study,result['original_artifact_id'])==raw
    return dict(actual_pypdf_version=packet['tool_version'],actual_parser_subprocess=True,parent_sys_path_only_dependency=True,inherited_pythonpath_fixture=False,original_bytes_unchanged=True,source_review_complete=False,internet_fetches=0)
   f.check('actual PDF extraction reads the private uploaded original with no synthetic URL',parser)
   def invalid():
    for invalid_data,stored in ((b'not a PDF',b'not a PDF'),(raw,raw+b'tampered')):
     item=body(invalid_data);paper_uploads.submit(f.ACTOR,item);stage(item,stored)
     f.rejects(lambda:paper_uploads.submit(f.ACTOR,dict(action='start',request_id=item['request_id'])))
     assert f.query('select status from research_paper_uploads where id='+f.sql_text(item['request_id']))=='rejected'
     assert f.query('select count(*) from research_autonomy_workflows where study_id='+f.sql_text(item['request_id']))=='0'
    return dict(invalid_signature_rejected=True,tampered_hash_or_size_rejected=True,failed_originals_retained=True)
   f.check('invalid or altered uploads retain rejection reasons without admitting work',invalid)
   def access():
    for role in ('anon','authenticated'):
     assert f.query("select has_table_privilege(current_user,'research_paper_uploads','SELECT,INSERT,UPDATE,DELETE')",role=role)=='f'
     assert f.query("select has_function_privilege(current_user,'research_paper_upload(text,uuid,uuid,jsonb)','EXECUTE')",role=role)=='f'
     assert f.query('select count(*) from research_studies where id='+f.sql_text(study),role=role)=='0'
    assert f.query("select relrowsecurity from pg_class where relname='research_paper_uploads'")=='t'
    bucket=json.loads(f.query("select row_to_json(b) from storage.buckets b where id='research-paper-uploads'"));assert bucket['public'] is False and bucket['file_size_limit']==10000000 and bucket['allowed_mime_types']==['application/pdf']
    f.rejects(lambda:f.query("update research_paper_uploads set paper='{}' where id="+f.sql_text(study),role='service_role'))
    f.rejects(lambda:f.query('delete from research_paper_uploads where id='+f.sql_text(study),role='service_role'))
    return dict(rls_enabled=True,browser_reads=False,browser_writes=False,browser_rpc=False,private_bucket=True,bucket_maximum_bytes=10000000,terminal_identity_immutable=True,remote_storage_enforcement_exercised=False)
   f.check('RLS RPC grants original identity and bucket configuration retain private access',access)
   def legacy():
    for kind in ('paper','idea'):
     document=dict(title='Legacy intake',paper_url='https://example.org/paper.pdf' if kind=='paper' else None,domain='Software',scope='Software fixture',origin_module=None)
     if kind=='idea':document['study_kind']='idea'
     uid=f.uid();payload=dict(p_actor=f.ACTOR,p_id=uid,p_document=document);assert f.rpc('research_create_study',payload)==f.rpc('research_create_study',payload)
    pending=body();paper_uploads.submit(f.ACTOR,pending);u=paper_uploads.owned(f.ACTOR,pending['request_id'])
    f.rejects(lambda:autonomy.start(f.ACTOR,dict(request_id=pending['request_id'],paper=u['paper'],autonomous=True)))
    return dict(legacy_url_and_idea_replay=True,unverified_direct_start_denied=True)
   f.check('legacy studies replay while direct unverified PDF starts are denied',legacy)
   def copies():
    original=autonomy.one('studies',study,study);target=f.uid();paper={key:original[key] for key in ('title','paper_url','paper_upload','domain','scope','origin_module','study_kind')};paper['title']='Private follow-up'
    copy=paper_uploads.create_private_study(f.ACTOR,target,paper,study);assert copy['id']==target and copy['paper_url'] is None
    assert paper_uploads.create_private_study(f.ACTOR,target,paper,study)['id']==target
    assert f.query('select count(*) from research_autonomy_workflows where study_id='+f.sql_text(target))=='0'
    copied=store.rows('artifacts',dict(study_id='eq.'+target))[0];assert store.artifact_bytes(target,copied['id'])==raw
    f.rejects(lambda:paper_uploads.create_private_study(f.OTHER,f.uid(),paper,study))
    return dict(owner_copy_hash_verified=True,duplicate_copy_idempotent=True,cross_owner_copy_denied=True,unrequested_autonomous_workflows=0)
   f.check('owner follow-up workspaces preserve uploaded paper bytes without launching new autonomy',copies)
  f.report['passed']=True
 except Exception as error:
  f.report.update(passed=False,error=str(error));raise
 finally:
  f.report['ended_at']=workflow.now();path=f.DIRECTORY/'paper-upload-validation-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(directory=str(f.DIRECTORY),passed=f.report.get('passed'),checks=len(f.report['checks']))))


if __name__=='__main__':main()
