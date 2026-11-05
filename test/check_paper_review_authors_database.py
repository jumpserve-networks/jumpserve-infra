"""Actual local author-confirmation transactions; no cloud or model calls."""
from concurrent.futures import ThreadPoolExecutor
import json,os,shutil,urllib.parse
import check_research_ideas_database as f
import workflow

MIGRATION='202611050002_paper_review_authors.sql'

def main():
 url=os.environ.get('UNLIMITED_DEFAULTS_TEST_DATABASE_URL')
 if url:
  parsed=urllib.parse.urlsplit(url)
  if parsed.hostname not in ('localhost','127.0.0.1') or parsed.path not in ('/postgres','/'):raise ValueError('Isolated localhost database required.')
  f.ORIGIN=urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,'/','',''));f.PSQL=shutil.which('psql') or f.PSQL
 f.bootstrap();raw=(f.ROOT/'database'/MIGRATION).read_bytes();f.query(raw.decode());f.report['migration_sha256'][MIGRATION]=workflow.digest(raw)
 q=f.sql_text;j=f.sql_json
 def js(sql):return json.loads(f.query(sql) or 'null')
 def review(c):return js('select to_jsonb(r) from research_paper_reviews r where study_id='+q(c['study']))
 def rpc(c,payload,actor=None):return f.rpc('research_paper_review',dict(p_operation='confirm',p_actor=actor or f.ACTOR,p_study=c['study'],p_payload=payload))
 def case():
  study,source,claim,task=[f.uid() for _ in range(4)]
  upload=dict(filename='Fixture upload.pdf',sha256='a'*64,byte_count=100)
  paper=dict(title='Fixture upload',domain='Pending paper review',scope='Synthetic software fixture',study_kind='paper',paper_url=None,paper_upload=upload)
  original=dict(version='paper-authors-v1',names=['Extracted Name'],page=1,method='Explicit synthetic software fixture')
  f.query('insert into research_studies(id,title,paper_url,domain,scope,study_kind,paper_upload) values('+','.join([q(study),q(paper['title']),'null',q(paper['domain']),q(paper['scope']),q('paper'),j(upload)])+');'+
   'insert into research_study_owners values('+q(study)+','+q(f.ACTOR)+');'+
   'insert into research_paper_uploads(id,owner_id,paper) values('+q(study)+','+q(f.ACTOR)+','+j(paper)+');'+
   'insert into research_autonomy_workflows(study_id,initial_prompt,initial_sha256) values('+q(study)+",'{}',encode(sha256(convert_to('{}','UTF8')),'hex'));"+
   'insert into research_sources(id,study_id,citation,kind,role,access_status,review_status,review_definition,examined,unexamined,retrieval_attempts,reviewer,findings,limitations) values('+','.join([q(source),q(study),q('Explicit synthetic source'),q('paper'),q('primary'),q('available'),q('retrieved-unreviewed'),q('Software fixture'),q(''),q('All'),j([]),j({}),q(''),q('Synthetic fixture')])+');'+
   'insert into research_claims(id,study_id,source_id,location,description,claim_type,scope,metrics,priority) values('+','.join([q(claim),q(study),q(source),q('Synthetic page 1'),q('Latency is 10 ms.'),q('numerical'),j({}),j([]),'1'])+');'+
   'insert into research_paper_reviews(study_id,status,revision,title,domain,metadata,seeds) values('+','.join([q(study),q('ready'),'4',q('Prepared title'),q('Networking'),j(dict(authors=original)),j([dict(id=task,claim_id=claim,context={})])])+')')
  payload=dict(title='Owner title',domain='Networking',revision=4,claim_ids=[claim],selection=dict(central_claims=[claim],testable_findings=[]),authors=['Doe, Jane','María José de la Cruz'])
  return dict(study=study,original=original,payload=payload)
 def concurrent():
  c=case();limits=f.query('select jsonb_build_array(initial_prompt,initial_sha256,deadline_at,max_spend_cents,committed_cents) from research_autonomy_workflows where study_id='+q(c['study']))
  claims=f.query('select jsonb_agg(to_jsonb(c)) from research_claims c where study_id='+q(c['study']))
  with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda _:rpc(c,c['payload']),range(3)))
  assert all(r['status']=='confirmed' and r['metadata']['owner_authors']['names']==c['payload']['authors'] for r in results)
  saved=review(c);assert saved['metadata']['authors']==c['original'];assert saved['metadata']['owner_selection']==c['payload']['selection']
  assert saved['revision']==7 and f.query('select count(*) from research_paper_review_events where study_id='+q(c['study']))=='4'
  assert f.query('select count(*) from research_autonomy_tasks where study_id='+q(c['study']))=='1'
  assert f.query('select jsonb_build_array(initial_prompt,initial_sha256,deadline_at,max_spend_cents,committed_cents) from research_autonomy_workflows where study_id='+q(c['study']))==limits
  assert f.query('select jsonb_agg(to_jsonb(c)) from research_claims c where study_id='+q(c['study']))==claims
  for changes in (dict(authors=list(reversed(c['payload']['authors']))),dict(title='Changed'),dict(revision=5)):
   f.rejects(lambda:rpc(c,c['payload']|changes))
 f.check('concurrent author confirmation is idempotent, source-preserving and shares original authorization',concurrent)
 def invalid():
  c=case();before=review(c)
  for names in (None,'Name',[None],[''],['a'*201],['mail@example.org'],['https://example.org'],['line\nbreak'],['Name']*101):
   f.rejects(lambda:rpc(c,c['payload']|dict(authors=names)));assert review(c)==before
  f.rejects(lambda:rpc(c,c['payload'],actor=f.OTHER));assert review(c)==before
  f.rejects(lambda:rpc(c,c['payload']|dict(revision=3)));assert review(c)==before
  f.query("update research_autonomy_workflows set status='cancelled' where study_id="+q(c['study']))
  f.rejects(lambda:rpc(c,c['payload']));assert review(c)==before
 f.check('invalid names, stale reviews, non-owners and cancellation leave no partial author edit',invalid)
 def clear_and_legacy():
  c=case();saved=rpc(c,c['payload']|dict(authors=[]));assert saved['metadata']['owner_authors']['names']==[];assert saved['metadata']['authors']==c['original']
  legacy=case();payload=dict(legacy['payload']);payload.pop('authors');saved=rpc(legacy,payload)
  assert 'owner_authors' not in saved['metadata'] and saved['metadata']['authors']==legacy['original']
  assert rpc(legacy,payload)['revision']==saved['revision']
 f.check('empty author edits remain explicit while legacy confirmations preserve extracted authors',clear_and_legacy)
 def private():
  for role in ('anon','authenticated','service_role'):
   assert f.query("select has_function_privilege(current_user,'research_paper_review_before_authors_v1(text,uuid,uuid,jsonb)','EXECUTE')",role=role)=='f'
  for role in ('anon','authenticated'):
   assert f.query("select has_function_privilege(current_user,'research_paper_review(text,uuid,uuid,jsonb)','EXECUTE')",role=role)=='f'
 f.check('browser roles and direct helper invocation cannot bypass owner confirmation',private)
 f.report.update(passed=True,protocol='paper-review-authors-v1',provider_calls=0,production_mutations=0)
 path=f.DIRECTORY/'paper-review-authors-report.json';path.write_text(json.dumps(f.report,indent=2)+'\n');print(json.dumps(dict(passed=True,checks=len(f.report['checks']),report=str(path),provider_calls=0,production_mutations=0)))

if __name__=='__main__':main()
