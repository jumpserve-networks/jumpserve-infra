"""Local public API -> real isolated Postgres RLS -> browser verification.

Only the persistence transport is replaced; the real public API handler and
snapshot logic run unchanged. No Google session or production system is mocked
into an authenticated state. Synthetic reviews are software fixtures only.
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import urllib.parse
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
import api, bridge, runner, store, workflow

PSQL='/opt/homebrew/opt/postgresql@17/bin/psql'
ACTOR='953f20a3-3fd8-4fb4-8844-5d4d72690e02'
IPV6='953f20a3-3fd8-4fb4-8844-5d4d72690e01'
NUMERIC='953f20a3-3fd8-4fb4-8844-5d4d72690e10'
def sql_text(value):return "'"+str(value).replace("'","''")+"'"
def sql_json(value):return sql_text(json.dumps(value,allow_nan=False))+'::jsonb'
def uid(study,name):return str(uuid.uuid5(uuid.UUID(study),name))

def numerical_fixture():
    source=uid(NUMERIC,'source')
    observed=[];published=[]
    for i in range(6):
        row=dict(observation_id=f'fixture-{i}',configuration_identity='A',metric='latency',units='ms',value=i,status='recorded',reason=None)
        published.append(dict(row,source_id=source,location=f'Golden software fixture row {i}',extraction='Synthetic reference value; not a paper result.'))
        if i==2:continue
        if i==1:row['value']=1.2
        if i==3:row['value']=True
        if i in (4,5):row.update(status='ambiguous' if i==4 else 'excluded',value=None,reason='Explicit software fixture state')
        observed.append(row)
    observed.append(dict(observation_id='unexpected',configuration_identity='B',metric='latency',units='ms',value=42,status='recorded',reason=None))
    raw=workflow.canonical(dict(published=published,observed=observed))
    document=workflow.numerical_protocol(workflow.digest(raw),'latency','ms',0.1,[dict(identity=c,details={'purpose':'Synthetic software fixture'}) for c in ('A','B')])
    document['prior_exposure']='Development fixtures designed with implementation; not independent scientific validation.'
    protocol=workflow.protocol_record(document,uid(NUMERIC,'protocol'))
    campaign=dict(id=uid(NUMERIC,'campaign'),protocol_id=protocol['id'],followup_of=None,title='Synthetic numerical software checks',stage='pilot',experiment_type='independent-check',adapter='matched-numeric-v1',planned_units=6,coverage_limits='Seven synthetic cells, no scientific inference.')
    source_row=dict(id=source,citation='Synthetic software regression fixture (not a research paper)',source_url='https://example.org/software-fixture',retrieved_url=None,kind='dataset',role='software regression',retrieved_version='v1',sha256=workflow.digest(raw),byte_count=len(raw),access_status='locally-generated',review_status='retrieved-unreviewed',review_definition='Software fixture; no substantive literature review.',examined='None',unexamined='Not literature',retrieval_attempts=[],reviewer={'identity':'AI implementer fixture','type':'AI','independence':'Not independent'},findings='Synthetic zero and non-recorded states.',limitations='No new empirical or published paper measurements.')
    result=runner.execute(raw,protocol,campaign,uid(NUMERIC,'run'))
    records=[dict(kind='sources',record=source_row),dict(kind='protocols',record=protocol),dict(kind='campaigns',record=campaign),dict(kind='runs',record=result['run'])]
    for kind in ('published_values','measurements','summaries'):records.extend(dict(kind=kind,record=row) for row in result[kind])
    claim=uid(NUMERIC,'claim')
    records.append(dict(kind='claims',record=dict(id=claim,source_id=source,location='Golden software fixture row 0',description='Synthetic zero cell is preserved and matches its reference.',claim_type='numerical',scope={'limit':'Software regression only; no research paper claim.'},metrics=['latency'],priority=1)))
    records.append(dict(kind='assessments',record=dict(id=uid(NUMERIC,'assessment'),claim_id=claim,campaign_id=campaign['id'],supersedes_id=None,label='reproduced',tested_conditions={'observation':'fixture-0','value':0,'units':'ms'},evidence=[{'run_id':result['run']['id']}],justification='Only the deterministic zero-cell regression; other fixture cells exercise unresolved states.',limitations='Synthetic fixture, not independent scientific validation.',reviewer={'identity':'AI implementer fixture','type':'AI','independence':'Not independent'})))
    return dict(paper=dict(title='Synthetic software comparison fixture',paper_url='https://example.org/software-fixture',domain='Software verification',scope='Development fixture; no paper claim validation.',origin_module=None),records=records)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',default='postgresql://michael@localhost:54477/jumpserve_research_browser_test')
    parser.add_argument('--port',type=int,default=4102)
    args=parser.parse_args()
    target=urllib.parse.urlsplit(args.database)
    if target.hostname not in ('localhost','127.0.0.1') or target.path!='/jumpserve_research_browser_test':raise SystemExit('Only the isolated local browser test DB is allowed.')
    if args.port!=4102:raise SystemExit('The fixture binds only loopback port 4102.')
    def query(sql):
        result=subprocess.run([PSQL,args.database,'-X','-v','ON_ERROR_STOP=1','-q','-t','-A'],input=sql,text=True,capture_output=True,timeout=10)
        if result.returncode:raise RuntimeError(result.stderr)
        return result.stdout.strip()
    empty=query("select count(*) from pg_tables where schemaname='public';")=='0'
    if not empty and query(f"select count(*) from research_studies where id not in ('{IPV6}','{NUMERIC}');")!='0':raise SystemExit('Fixture cannot amend an unrelated database.')
    setup="""begin;
do $$ begin create role anon; exception when duplicate_object then null; end $$;
do $$ begin create role authenticated; exception when duplicate_object then null; end $$;
do $$ begin create role service_role bypassrls; exception when duplicate_object then null; end $$;
grant usage on schema public to anon,authenticated,service_role;
create schema storage;
create table storage.buckets(id text primary key,name text,public boolean);
create table storage.objects(id integer primary key,bucket_id text);
alter table storage.objects enable row level security;
grant usage on schema storage to anon,authenticated,service_role;
grant all on storage.objects to anon,authenticated,service_role;
commit;"""
    if empty:
        query(setup)
        query((ROOT/'database/202610070001_research_workflow.sql').read_text())
    assessment=ROOT.parent/'jumpserve-back-end/experiments/ipv6_dns/evidence/assessment-v2.json'
    package=bridge.ipv6(assessment,IPV6)
    for study,data in ((IPV6,package),(NUMERIC,numerical_fixture())):
        query(f"select research_create_study('{ACTOR}','{study}',{sql_json(data['paper'])});")
        # Resume an interrupted local fixture without replacing any saved bytes.
        missing=[entry for entry in data['records'] if query(f"select count(*) from research_{entry['kind']} where id='{entry['record']['id']}';")=='0']
        if missing:query(f"select research_append_bundle('{study}','{ACTOR}',{sql_json(missing)});")
        revision=workflow.digest(query(f"select research_evidence_manifest('{study}');").encode())[:16]
        reviews=[]
        for scope in ('scientific','software'):
            judgments={'scope_and_limits_reviewed':True} if scope=='scientific' else {'release_blockers':{key:True for key in ('database','backend','frontend','provenance','access_control')}}
            reviews.append(dict(kind='reviews',record=dict(id=uid(study,scope+revision),scope=scope,status='passed',reviewer={'identity':'AI browser fixture','type':'AI','independence':'Implementer; synthetic publication-control fixture'},judgments=judgments,limitations='Isolated browser fixture judgments; not an actual scientific review or production publication.')))
        query(f"select research_append_bundle('{study}','{ACTOR}',{sql_json(reviews)});")
        query(f"select research_publish('{study}','{ACTOR}','{uid(study,'publication'+revision)}','{uid(study,'scientific'+revision)}','{uid(study,'software'+revision)}','Local software fixture only');")
    # Query transport supports the actual store.rows projection/filter interface.
    def persistence(path,method='GET',body=None,public=False,raw=False):
        if method!='GET' or body is not None or raw:raise store.StoreError('Read-only browser fixture transport.')
        parsed=urllib.parse.urlsplit(path);table=parsed.path.removeprefix('/rest/v1/')
        if table not in ['research_'+kind for kind in (*workflow.PUBLIC_KINDS,'studies')]:raise store.StoreError('Unsupported fixture relation.')
        parameters=dict(urllib.parse.parse_qsl(parsed.query));columns=parameters.pop('select').split(',')
        if any(not column.replace('_','').isalnum() for column in columns):raise store.StoreError('Invalid fixture projection.')
        limit=int(parameters.pop('limit','1000'));offset=int(parameters.pop('offset','0'));order=parameters.pop('order','created_at.asc,id.asc')
        if not 0<=limit<=1000 or not 0<=offset<=10000:raise store.StoreError('Fixture query bound exceeded.')
        ordering=[]
        for item in order.split(','):
            column,direction=item.split('.')
            if column not in ('created_at','id','version') or direction not in ('asc','desc'):raise store.StoreError('Invalid ordering.')
            ordering.append(column+' '+direction)
        predicates=[]
        for column,value in parameters.items():
            if column not in ('id','study_id','created_at'):raise store.StoreError('Unexpected fixture filter.')
            operator,argument=value.split('.',1)
            if operator not in ('eq','lte'):raise store.StoreError('Unexpected fixture operator.')
            predicates.append(column+(' = ' if operator=='eq' else ' <= ')+sql_text(argument))
        where=' where '+' and '.join(predicates) if predicates else ''
        sql=f"begin; set local role {'anon' if public else 'service_role'}; select coalesce(json_agg(t),'[]'::json) from (select {','.join(columns)} from {table}{where} order by {','.join(ordering)} limit {limit} offset {offset}) t; rollback;"
        return json.loads(query(sql))
    store.request=persistence
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed=urllib.parse.urlsplit(self.path)
            # Explicit transport-failure fixtures, separate from SQL evidence.
            if parsed.path.endswith('/953f20a3-3fd8-4fb4-8844-5d4d72690e99'):
                self.send_error(503,'Synthetic unavailable transport fixture');return
            if parsed.path.endswith('/953f20a3-3fd8-4fb4-8844-5d4d72690e98'):
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"study":{"id":"invalid-fixture"},"records":{},"coverage":{},"access":"published-snapshot"}');return
            event=dict(rawPath=parsed.path,headers={},queryStringParameters=dict(urllib.parse.parse_qsl(parsed.query)),requestContext={'http':{'method':'GET'}})
            result=api.handler(event)
            self.send_response(result['statusCode'])
            for key,value in result['headers'].items():self.send_header(key,value)
            self.end_headers();self.wfile.write(result['body'].encode())
        def do_POST(self):self.send_error(401,'No authenticated session in this read-only fixture')
    print(json.dumps(dict(status='ready',origin='http://127.0.0.1:4102',database=target.path,ipv6_study=IPV6,numeric_fixture=NUMERIC,original_sha256=package['provenance']['original_sha256'],transport='actual public api.handler and store.snapshot; isolated SQL adapter uses role anon',authenticated_google_session=False)),flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
if __name__=='__main__':main()
