"""Three fixed private release checks; never accepts arbitrary source or targets."""
import argparse, datetime as dt, hashlib, importlib.util, json, os
from pathlib import Path
import subprocess, sys, time, uuid

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/guided-network-release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
import store,workflow,network_spec,network_execution,scheduler
ACTOR=str(uuid.uuid5(uuid.NAMESPACE_URL,'jumpserve:service-only:guided-network-release:2026-10-14:v2'))
DOMAIN='Private deployment operational check 2026-10-14 v3'
SOURCE='''import http.server,json,os,pathlib,threading,time,urllib.request
root=pathlib.Path(os.environ['JUMPSERVE_OUTPUT']).parent
spec=json.loads(pathlib.Path(os.environ['JUMPSERVE_SPEC']).read_text())
if spec['config']['parameters']['case']!='success':
 print('Overlong package started for a bounded operational cleanup check.',flush=True)
 time.sleep(10000)
class Handler(http.server.BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(b'own-host-operational-check')
 def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
threading.Thread(target=server.serve_forever,daemon=True).start()
rows=[]
for i in range(3):
 tick=time.perf_counter_ns()
 with urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port)+'/',timeout=5) as response:
  elapsed=(time.perf_counter_ns()-tick)/1e6;status=response.status;response.read()
 rows.append(dict(observation_key=str(i),metric='response_headers_ms',units='ms',value=elapsed,status='recorded',reason=None,metadata=dict(http_status=status,target='own-host-loopback')))
server.shutdown()
pathlib.Path(os.environ['JUMPSERVE_OUTPUT']).write_text(json.dumps(dict(version='network-observations-v1',observations=rows,provenance=dict(purpose='Private operational release check; no CDN or research-idea conclusion',python_version=__import__('sys').version),usage=None)))
print('Three own-host HTTP observations produced.',flush=True)
'''
def uid():return str(uuid.uuid4())
def persist_case(case,wall,directory):
    # This is a service administration principal, not an invented Google user.
    study,protocol,campaign,source_id,claim_id,job=[uid() for _ in range(6)]
    store.rpc('research_create_study',dict(p_actor=ACTOR,p_id=study,p_document=workflow.paper_details(dict(title='Private operational '+case+' check 2026-10-14 v3',domain=DOMAIN,scope='Service-admin deployment check. Not a user research idea, paper assessment or model evaluation.',study_kind='idea',paper_url=None))))
    package=network_execution.upload(study,ACTOR,dict(request_id=uid(),source=SOURCE,version='release-operational-v3'))
    p=workflow.numerical_protocol(workflow.digest(SOURCE.encode()),'response_headers_ms','ms',0,[dict(identity=case,details=dict(test_config=dict(mode='real-world',package=package,arguments=[],parameters=dict(case=case))))],max_observations=3)
    p.update(questions=['Does the '+case+' private operational case meet its declared deployment criterion?'],hypotheses='Successful case retains three real loopback HTTP observations; deadline and cancellation cases terminate the host under the declared bounds.',metrics=[dict(name='response_headers_ms',units='ms',planned_observations=3,lower_bound=0)],planned_units=1,data_origin='new-empirical',dates_or_epochs='2026-10-14 production release checks',algorithms=['Exact hash-pinned package and existing executor/runtime revisions; no statistical inference'],controls=['One dedicated t3.medium per case, no instance IAM profile, metadata disabled, no inbound security-group access','Queue polling paused while independent cleanup remains scheduled'],replication_unit='One operational host; cases are different controls, not independent scientific replications.',sample_size_rationale='One host for each of three distinct release requirements; deterministic pass criteria, no population precision claim.',exclusions='No exclusions or retries; failed checks and missing output remain recorded.',missing_data='Missing runtime output stays missing; no fabricated observations or imputation.',statistics='Exact count/units/hash and terminal-state checks. Timing values descriptive only; no inferential interval.',dependence='Three loopback requests on one host are related; no independence asserted.',prior_exposure='Development tests and source inspection occurred earlier; these are operational checks, not held-out scientific validation.',coverage_limits='No Google session, actual AI answer, multi-region or commercial CDN hypothesis validation.',stopping_rule='At most '+str(wall)+' seconds plus 180-second cleanup observation grace; terminate task-owned host on failure.')
    p['resource_limits'].update(wall_seconds=wall,max_input_bytes=256000,cost_basis='EC2 operational release budget; measured charges unknown.')
    p['execution']=dict(version=network_spec.VERSION,runner='custom-package-v1',replications=1,limits=dict(wall_seconds=wall,max_instances=1,max_output_bytes=1000000,max_network_bytes=100000000),exclusive_resources=['release:network-package-operational'])
    p=network_spec.bind_inputs(p);workflow.validate_protocol(p);n=network_spec.specs(p)[0]
    source=dict(id=source_id,citation='Guided networking release protocol v1 and amendments v2/v3; private operational source',source_url=None,retrieved_url=None,kind='software',role='Original executable operational protocol',retrieved_version='release-operational-v3',sha256=workflow.digest(SOURCE.encode()),byte_count=len(SOURCE.encode()),access_status='locally-generated',review_status='retrieved-unreviewed',review_definition='Source and protocol bytes preserved; no literature or independent review claimed.',examined='Operational pass criteria and configuration reviewed by AI implementer.',unexamined='Independent scientific and human review.',retrieval_attempts=[],reviewer=dict(identity='Primary Codex AI implementer',type='AI',independence='Not independent; release implementer'),findings='No outcome yet.',limitations='Deployment check only.')
    claim=dict(id=claim_id,source_id=source_id,location='Operational release protocol',description='The '+case+' executor meets its declared deployment criterion.',claim_type='operational',scope=dict(purpose='private-release-operation',service_actor=ACTOR),metrics=p['metrics'],priority=1)
    campaign_row=dict(id=campaign,protocol_id=protocol,followup_of=None,title='Private '+case+' deployment check',stage='pilot',experiment_type='independent-check',adapter='network-execution-v1',planned_units=1,coverage_limits=p['coverage_limits'])
    entries=[dict(kind='sources',record=source),dict(kind='claims',record=claim),dict(kind='protocols',record=workflow.protocol_record(p,protocol)),dict(kind='campaigns',record=campaign_row),dict(kind='claim_checks',record=dict(id=uid(),claim_id=claim_id,campaign_id=campaign,method='Fixed service-only operational host check; no model-readiness declaration',applicability='applicable',rationale='Necessary before enabling custom package admission.'))]
    store.append_bundle(study,ACTOR,entries)
    body=dict(request_id=job,campaign_id=campaign,execution_mode='automatic',priority=1,dependencies=[],exclusive_resources=p['execution']['exclusive_resources'],rationale='Declared private service-only release check; not Google-authenticated user activity.',raw_input=workflow.canonical(n).decode())
    scheduler.enqueue(study,ACTOR,body)
    leased=store.rpc('research_queue_claim',dict(p_worker=uid()))
    if leased is None or leased['id']!=job:raise RuntimeError('Operational job did not receive the expected lease; do not claim another job')
    store.rpc('research_network_begin',dict(p_job=job,p_token=leased['lease_token'],p_spec=n,p_sha=workflow.digest(workflow.canonical(n))))
    (directory/'protocol.json').write_bytes(workflow.canonical(p));(directory/'package.py').write_bytes(SOURCE.encode());(directory/'spec.json').write_bytes(workflow.canonical(n))
    return dict(study=study,job=job,lease=leased,spec=n,protocol=protocol,wall_seconds=wall)
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('case',choices=['success','deadline','cancellation']);args=parser.parse_args()
    directory=ROOT/'.test-artifacts/guided-network/operational'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,exist_ok=False)
    report=dict(protocol='guided-network-release-amendment-v3',case=args.case,started_at=release.stamp(),status='running',reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),authentication='Service administration, no Google session or fabricated model reviews',measured_charges_usd=None,observations=[])
    def save(): (directory/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    paused=None;execution=None;instances=[];save()
    try:
        report['targets']=release.previous.target()
        credentials=release.aws('configure','export-credentials','--format','process')
        os.environ.update(AWS_ACCESS_KEY_ID=credentials['AccessKeyId'],AWS_SECRET_ACCESS_KEY=credentials['SecretAccessKey'],AWS_SESSION_TOKEN=credentials['SessionToken'],AWS_DEFAULT_REGION='us-east-1',SUPABASE_URL='https://regphejnlvfpyokpniny.supabase.co',SUPABASE_SERVICE_ROLE_KEY=release.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'],SSL_CERT_FILE='/etc/ssl/cert.pem')
        resources=release.aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
        pick=lambda start:next(r['PhysicalResourceId'] for r in resources if r['LogicalResourceId'].startswith(start))
        executor=pick('ResearchWorkflowPackageExecutor32');reaper=pick('ResearchWorkflowPackageReaperED');rule=pick('ResearchWorkflowQueuePoll')
        os.environ['NETWORK_PACKAGE_FUNCTION']='arn:aws:lambda:us-east-1:395567831870:function:'+executor
        if release.admin.query("select count(*) count from research_queue_jobs where status in ('queued','running')")[0]['count']:raise RuntimeError('Existing production queue work prevents isolated operational check')
        existing=store.rows('studies',dict(domain='eq.'+DOMAIN))
        if len(existing)>=3 or any(args.case in row['title'] for row in existing):raise RuntimeError('Original operational case already exists or three-host budget exhausted; preserve it and declare a versioned follow-up')
        state=release.aws('events','describe-rule','--name',rule)['State']
        if state!='ENABLED':raise RuntimeError('Queue rule was not enabled; do not change an existing pause')
        subprocess.check_call(['aws','events','disable-rule','--name',rule,'--profile','jumpserve','--region','us-east-1']);paused=rule
        execution=persist_case(args.case,900 if args.case=='cancellation' else 300,directory)
        report['execution']={k:v for k,v in execution.items() if k not in ('lease','spec')};save()
        import boto3
        client=boto3.client('lambda',region_name='us-east-1');ec2=boto3.client('ec2',region_name='us-east-1')
        def invoke(name,body):
            response=client.invoke(FunctionName=name,Payload=workflow.canonical(body));data=response['Payload'].read()
            if response.get('FunctionError'):raise RuntimeError('Private Lambda failed: '+data.decode()[:300])
            return json.loads(data)
        message=lambda action:dict(source='jumpserve.network-execution',job_id=execution['job'],action=action)
        invoke(executor,message('launch'))
        before=time.monotonic();cancelled=False;terminal=None
        while time.monotonic()-before<execution['wall_seconds']+180:
            found=ec2.describe_instances(Filters=[dict(Name='tag:Project',Values=['JumpServeNetworkPackage']),dict(Name='tag:NetworkExecutionId',Values=[execution['job']])])
            instances=[i for group in found['Reservations'] for i in group['Instances']]
            if len(instances)>1:raise RuntimeError('Duplicate cloud instance for one saved invocation')
            if instances:
                machine=instances[0];state=machine['State']['Name']
                if machine.get('IamInstanceProfile') or machine['MetadataOptions']['HttpEndpoint']!='disabled':raise RuntimeError('Guest credentials or metadata isolation differs')
                report['instance']=dict(id=machine['InstanceId'],state=state,type=machine['InstanceType'],image=machine['ImageId'],zone=machine['Placement']['AvailabilityZone'],iam_profile=None,metadata='disabled')
            n=store.rpc('research_network_launch',dict(p_job=execution['job'],p_runner='custom-package-v1',p_claim=False))
            report['observations'].append(dict(at=release.stamp(),phase=n['phase'],instance_state=instances[0]['State']['Name'] if instances else None,output_available='output' in n['data']))
            if args.case=='cancellation' and instances and state=='running' and not cancelled:
                store.rpc('research_network_cancel',dict(p_study=execution['study'],p_actor=ACTOR,p_job=execution['job'],p_id=uid(),p_reason='Private operational cancellation with queue poll paused and guest deadline still in future.'))
                answer=invoke(reaper,{})
                report['independent_reaper']=answer;report['deadline_future_at_cancellation']=dt.datetime.fromisoformat(n['deadline'].replace('Z','+00:00')).timestamp()>time.time();cancelled=True
            if args.case!='cancellation':
                answer=invoke(executor,message('status'))
                if answer.get('status') in ('completed','failed','cancelled'):terminal=answer;break
            elif instances and state=='terminated':
                answer=invoke(reaper,{})
                n=store.rpc('research_network_launch',dict(p_job=execution['job'],p_runner='custom-package-v1',p_claim=False))
                if n['phase']=='cancelled':terminal=n['data'];report['independent_reaper_terminal']=answer;break
            save();time.sleep(10)
        if terminal is None:raise RuntimeError('Terminal cleanup was not confirmed within the declared observation bound')
        report['terminal_status']=terminal['status'];report['actual_resources']=terminal.get('resources')
        finished=network_execution.advance(execution['lease'],store.rows('campaigns',dict(id='eq.'+execution['lease']['campaign_id'],study_id='eq.'+execution['study']))[0],store.rows('protocols',dict(id='eq.'+execution['protocol'],study_id='eq.'+execution['study']))[0],workflow.canonical(execution['spec']))
        report['queue_status']=finished['status'];rows=store.rows('measurements',dict(study_id='eq.'+execution['study']));report['measurement_count']=len(rows)
        if args.case=='success' and (terminal['status']!='completed' or len(rows)!=3 or any(r['units']!='ms' or r['status']!='recorded' for r in rows)):raise RuntimeError('Successful package did not retain exactly three valid millisecond observations')
        if args.case=='deadline' and terminal['status']!='failed':raise RuntimeError('Overlong package was not recorded as failed')
        if args.case=='cancellation' and (terminal['status']!='cancelled' or not report['deadline_future_at_cancellation']):raise RuntimeError('Independent early cancellation failed')
        originals=[]
        for record in store.rows('artifacts',dict(study_id='eq.'+execution['study'])):
            raw=store.artifact_bytes(execution['study'],record['id'],maximum=1000000)
            (directory/('original-'+record['sha256'])).write_bytes(raw)
            originals.append(dict(sha256=record['sha256'],bytes=len(raw),retrieval_hash_verified=True,provenance=record['provenance']))
        report['original_artifacts']=originals;report['scientific_assessments']=len(store.rows('assessments',dict(study_id='eq.'+execution['study'])));report['status']='passed'
    except BaseException as error:report.update(status='failed',reason=str(error));raise
    finally:
        if instances:
            import boto3
            ec2=boto3.client('ec2',region_name='us-east-1')
            owned=[i['InstanceId'] for i in instances if i['State']['Name'] not in ('terminated','shutting-down')]
            if owned:ec2.terminate_instances(InstanceIds=owned);report['finally_termination_requested']=owned
        if paused:subprocess.check_call(['aws','events','enable-rule','--name',paused,'--profile','jumpserve','--region','us-east-1']);report['queue_poll_restored']=True
        report['ended_at']=release.stamp();save();print(json.dumps(dict(directory=str(directory),case=args.case,status=report['status'],reason=report.get('reason'))))
if __name__=='__main__':main()
