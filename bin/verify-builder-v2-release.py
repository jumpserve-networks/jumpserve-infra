"""Fixed-target builder production smoke and evidence retrieval; no inference."""
import argparse,base64,datetime as dt,hashlib,importlib.util,io,json,pathlib,re,shlex,urllib.error,urllib.request,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/builder-production-v2'
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['native','recover-native','collect-native','restart','executor','activated','restore-polling','record']);args=parser.parse_args()
    BASE.mkdir(parents=True,exist_ok=True);out=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir()
    report=dict(protocol='experiment-builder-production-v2',mode=args.mode,status='running',targets=r.target(),measured_charges_usd=None)
    try:
        if args.mode=='record':
            release=json.loads((ROOT/'docs/experiment-builder-production-v2-status.json').read_bytes())
            assert release['status']=='deployed-with-conditional-verification-gap' and release['release_blocking_checks_passed']
            browser=json.loads((BASE/'browser/report.json').read_bytes());assert browser['passed']
            results=[json.loads(p.read_bytes()) for p in BASE.glob('*/receipt.json')]
            assert any(x.get('mode')=='activated' and x['status']=='complete' for x in results)
            assert any(x.get('native_control')=='passed' and x['status']=='complete' for x in results)
            files={}
            for p in BASE.rglob('*'):
                if p.is_file() and p.name!='release-evidence.zip':files[str(p.relative_to(ROOT))]=p.read_bytes()
            for dirname in ('openclaw-release','experiment-builder-release'):
                for directory in (ROOT/'.test-artifacts'/dirname).iterdir():
                    if not directory.is_dir() or directory.name<'20261027T235016990592Z':continue
                    for p in directory.iterdir():
                        if p.is_file() and (p.name in ('receipt.json','cdk.log','outputs.json','stack-before.json','stack-after.json','parameter-comparison.json') or p.suffix=='.zip'):
                            files[str(p.relative_to(ROOT))]=p.read_bytes()
            for name in ('docs/experiment-builder-production-v2-status.json','docs/experiment-builder-production-v2-protocol.json','docs/experiment-builder-production-v2.md','docs/experiment-builder-qualification-artifacts-v2.json','research-workflow-runtime.json','database/202610270006_experiment_builder_prompt_v2.sql','database/202610270007_experiment_builder_v2_publication.sql','bin/check_builder_production_host.py','bin/verify-builder-v2-release.py'):
                files[name]=(ROOT/name).read_bytes()
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
                for name,raw in sorted(files.items()):z.writestr(name,raw)
                z.writestr('artifact-manifest.json',json.dumps([dict(path=n,sha256=r.sha(raw),bytes=len(raw)) for n,raw in sorted(files.items())],sort_keys=True,separators=(',',':')))
            raw=buffer.getvalue();assert len(raw)<=32000000
            object_path='release-verification/experiment-builder-v2/final/'+r.sha(raw)+'.zip'
            key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'];headers={'apikey':key,'Authorization':'Bearer '+key}
            url='https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+object_path
            with r.prior.guard.OPEN.open(urllib.request.Request(url,data=raw,headers={**headers,'Content-Type':'application/zip'},method='POST'),timeout=60) as response:response.read(1000)
            with r.prior.guard.OPEN.open(urllib.request.Request(url,headers=headers),timeout=60) as response:restored=response.read(32000001)
            assert restored==raw
            with zipfile.ZipFile(io.BytesIO(restored)) as z:
                for entry in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(entry['path']))==entry['sha256']
            (out/'release-evidence.zip').write_bytes(raw);item=dict(bucket='research-workflow-raw',path=object_path,sha256=r.sha(raw),retrieved_sha256=r.sha(restored),bytes=len(raw),members=len(files),public=False)
            evaluation=dict(protocol='experiment-builder-production-v2',kind='operational-release-verification',status='deployed-with-conditional-verification-gap',release=release,browser=browser,archive=item,live_provider_calls=0,scientific_claims_assessed=0,reviewer=dict(identity='Primary Codex AI implementation author',type='AI',independent=False),measured_charges_usd=None)
            evaluation_raw=json.dumps(evaluation,sort_keys=True,separators=(',',':'));digest=r.sha(evaluation_raw.encode())
            # Existing schema permits passed/failed-substantive-review/failed-or-paused.
            # The report's kind/status distinguish these passed release checks
            # from prompt qualification and retain the conditional auth gap.
            row=dict(prompt_version_id='dfab5ecb-b8b9-5ad3-8771-f28a06b53b27',outcome='passed',report_raw=evaluation_raw,report_sha256=digest,original_artifacts=item,recorded_by='Primary Codex AI implementation author; nonindependent, not human review')
            report['archive']=item
            (out/'requested-evaluation.json').write_text(json.dumps(row,indent=2)+'\n')
            origin='https://regphejnlvfpyokpniny.supabase.co/rest/v1/agent_prompt_evaluations'
            request=urllib.request.Request(origin+'?on_conflict=prompt_version_id,report_sha256',data=json.dumps(row).encode(),headers={**headers,'Content-Type':'application/json','Prefer':'resolution=ignore-duplicates,return=minimal'},method='POST')
            try:
                with r.prior.guard.OPEN.open(request,timeout=60) as response:response.read(1000)
            except urllib.error.HTTPError as error:
                detail=json.loads(error.read(100000));report['database_error']={k:detail.get(k) for k in ('code','message')};raise
            with r.prior.guard.OPEN.open(urllib.request.Request(origin+'?report_sha256=eq.'+digest+'&select=report_raw',headers=headers),timeout=60) as response:rows=json.loads(response.read(1000001))
            assert len(rows)==1 and r.sha(rows[0]['report_raw'].encode())==digest
            report.update(archive=item,evaluation_sha256=digest,retrieved_evaluation_sha256=digest,live_provider_calls=0,scientific_claims_assessed=0)
            (ROOT/'docs/experiment-builder-production-v2-artifacts.json').write_text(json.dumps(dict(protocol=report['protocol'],archive=item,evaluation_sha256=digest,retrieved_evaluation_sha256=digest,public=False),indent=2)+'\n')
        elif args.mode=='restore-polling':
            config=r.aws('lambda','get-function-configuration','--function-name',r.functions()['api'])['Environment']['Variables']
            assert config['RESEARCH_AUTONOMY_ENABLED']=='true' and config['RESEARCH_BUILDER_ENABLED']=='true'
            assert r.admin.query("select active_version_id from agent_prompt_settings where module_id='research-experiment-builder'")==[dict(active_version_id='dfab5ecb-b8b9-5ad3-8771-f28a06b53b27')]
            resources=r.aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
            rules=[x for x in resources if x['ResourceType']=='AWS::Events::Rule' and x['LogicalResourceId'].startswith('ResearchWorkflowAutonomyPoll')];assert len(rules)==1
            name=rules[0]['PhysicalResourceId'];before=r.aws('events','describe-rule','--name',name)['State']
            if before!='ENABLED':r.aws('events','enable-rule','--name',name)
            after=r.aws('events','describe-rule','--name',name)['State'];assert after=='ENABLED'
            report.update(rule=rules[0]['LogicalResourceId'],before=before,after=after,reason='Explicitly restore the exact manual maintenance hold; unchanged CloudFormation properties do not repair this drift.')
        elif args.mode=='activated':
            manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes())
            functions=r.prior.functions(out,True);policy=json.loads((BACK/'research_workflow/policies/built-package-costs-v2.json').read_bytes())
            expected_policy=r.sha(json.dumps(policy,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
            checked=[]
            for function in functions:
                config=r.aws('lambda','get-function-configuration','--function-name',function['function']);env=config['Environment']['Variables']
                if function['logical_id'].startswith(('ResearchWorkflowApi','ResearchWorkflowAutonomyWorker')):
                    assert env['RESEARCH_BUILDER_ENABLED']=='true' and env['RESEARCH_AUTONOMY_ENABLED']=='true' and env['RESEARCH_AI_RUNTIME']=='openclaw-production-v1'
                assert env['NETWORK_BUILT_PACKAGE_POLICY_SHA256']==expected_policy and 'NETWORK_PACKAGE_FUNCTION' not in env
                assert re.fullmatch(r'arn:aws:lambda:us-east-1:395567831870:function:[A-Za-z0-9_-]+:[1-9][0-9]*',env['NETWORK_BUILT_PACKAGE_FUNCTION'])
                checked.append(dict(function=function['function'],zip_sha256=function['zip_sha256'],source_files_verified=len(function['source_hashes']),built_executor=env['NETWORK_BUILT_PACKAGE_FUNCTION'],policy_sha256=expected_policy,custom_packages_enabled=False))
            report['functions']=checked
            # Confirmation metadata/history were explicitly made service-only
            # by 202610230002. The historical queue verifier predates them.
            r.prior.PRIVATE|={'research_model_workers','research_model_dispatches','research_builder_calls','research_builder_packages','research_shared_campaigns','research_shared_campaign_members','research_paper_reviews','research_paper_review_events'}
            report['security']=r.prior.security()
            prompts=r.admin.query("select s.module_id,v.id,v.version,v.content_sha256,v.published_at from agent_prompt_settings s join agent_prompt_versions v on v.id=s.active_version_id where s.module_id in ('research-autonomy','research-experiment-builder') order by s.module_id")
            assert len(prompts)==2 and prompts[0]['version']=='research-autonomy-v10' and prompts[1]['id']=='dfab5ecb-b8b9-5ad3-8771-f28a06b53b27' and prompts[1]['published_at']
            qualification=json.loads((ROOT/'docs/experiment-builder-actual-answer-review-v2.json').read_bytes());assert prompts[1]['content_sha256']==qualification['prompt_sha256'];report['prompts']=prompts
            with r.prior.guard.OPEN.open('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/capabilities',timeout=30) as response:raw=response.read(2000000)
            (out/'capabilities.json').write_bytes(raw);cap=json.loads(raw)
            assert cap['autonomy']['enabled'] and cap['autonomy']['defaults']['attempts_per_claim'] is None and cap['autonomy']['runtime']['runtime']=='openclaw-production-v1'
            assert next(x for x in cap['networking']['runners'] if x['id']=='built-package-v1')['enabled']
            assert not next(x for x in cap['networking']['runners'] if x['id']=='custom-package-v1')['enabled']
            report['capabilities']=dict(sha256=r.sha(raw),autonomy_enabled=True,built_package_enabled=True,ai_turn_limit=None,runtime=cap['autonomy']['runtime'])
            resources=r.aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries'];polls=[]
            for item in resources:
                if item['ResourceType']=='AWS::Events::Rule' and item['LogicalResourceId'].startswith(('ResearchWorkflowAutonomyPoll','ResearchWorkflowQueuePoll')):
                    state=r.aws('events','describe-rule','--name',item['PhysicalResourceId'])['State'];assert state=='ENABLED';polls.append(dict(logical_id=item['LogicalResourceId'],state=state))
            assert len(polls)==2;report['polling']=polls
            assert r.instance()=='i-087f1493809643115';report['preserved_worker']=r.instance()
        elif args.mode=='executor':
            resources=r.aws('cloudformation','list-stack-resources','--stack-name','JumpServeBenchmarkStack')['StackResourceSummaries']
            name=next(x['PhysicalResourceId'] for x in resources if x['ResourceType']=='AWS::Lambda::Function' and x['LogicalResourceId'].startswith('ResearchWorkflowPackageExecutor'))
            original=r.aws('lambda','get-function','--function-name',name);config=original['Configuration']
            assert config['Handler']=='network_package.handler' and config['Runtime']=='python3.12' and config['MemorySize']==512 and config['Timeout']==60
            assert config['Environment']['Variables']['NETWORK_PACKAGE_AMI']=='ami-033ea4ff4a9c726dc'
            with r.prior.guard.OPEN.open(original['Code']['Location'],timeout=60) as response:raw=response.read(8000001)
            assert len(raw)<=8000000 and base64.b64encode(hashlib.sha256(raw).digest()).decode()==config['CodeSha256']
            (out/'deployed-executor.zip').write_bytes(raw)
            files=('network_package.py','store.py','workflow.py','network_spec.py','package_runtime.py','generated_package.py','netem_iperf.py')
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                hashes={n:r.sha(z.read(n)) for n in files}
            assert hashes=={n:r.sha((BACK/'research_workflow'/n).read_bytes()) for n in files}
            report.update(function=name,zip_sha256=r.sha(raw),unchanged_execution_files=hashes,handler=config['Handler'],ami='ami-033ea4ff4a9c726dc',scope='Executor source and direct deployment/guest dependencies match the retained lifecycle controls. Other bundled files and immutable Lambda version can differ; no new EC2 experiment claimed.')
        elif args.mode=='restart':
            r.auth_maintenance_guard()
            report['ssm']=r.ssm(['set -eu','systemctl restart jumpserve-openclaw.service','systemctl is-active jumpserve-openclaw.service'])
        elif args.mode=='recover-native':
            original=json.loads((BASE/'native-command.json').read_bytes());host=original['host'];assert host.startswith('/var/lib/jumpserve-openclaw/builder-production-v2/')
            old=r.aws('ssm','get-command-invocation','--command-id',original['ssm']['command_id'],'--instance-id',original['ssm']['instance_id']);assert old['Status']=='Failed' and 'assert len(raw)<=20000000' in old['StandardErrorContent']
            files={'recover.py':(ROOT/'bin/check_builder_production_host.py').read_bytes(),'original-archive-failure.json':json.dumps(old,sort_keys=True).encode()}
            install="from pathlib import Path;import base64,json;p=Path("+repr(host)+");assert json.loads((p/'report.json').read_bytes())['status']=='passed';files="+repr({n:base64.b64encode(raw).decode() for n,raw in files.items()})+"\nfor n,v in files.items():\n q=p/n;assert not q.exists();q.write_bytes(base64.b64decode(v));q.chmod(0o644)"
            report['ssm']=r.ssm(['set -eu','python3.12 -c '+shlex.quote(install),'set -a','. /etc/jumpserve-openclaw.env','set +a','runuser -u jumpserve -- /opt/jumpserve/python/bin/python -B '+host+'/recover.py']);report['host']=host;report['reexecuted_native_control']=False;report['original_command']=original['ssm']
            (BASE/'native-command-before-evidence-recovery.json').write_text(json.dumps(original,indent=2)+'\n')
            (BASE/'native-command.json').write_text(json.dumps(report,indent=2)+'\n')
        elif args.mode=='native':
            manifest=json.loads((ROOT/'research-workflow-runtime.json').read_bytes());assert manifest['source_revision']=='f5453c866bfd74e770398fd6adfebae3265b01c6'
            host='/var/lib/jumpserve-openclaw/builder-production-v2/'+out.name
            files={'check.py':(ROOT/'bin/check_builder_production_host.py').read_bytes()}
            for name in ('check_experiment_builder_linux.py','prepare_builder_vendor.py'):
                files['research_workflow/tests/'+name]=(BACK/'research_workflow/tests'/name).read_bytes()
            files['expected.json']=json.dumps(dict(files=manifest['files'],image='sha256:ef390fb5c927fc11773da987e96c3264b618118fd39b8715139cf977b1b4320a',test_files={n:r.sha(raw) for n,raw in files.items() if n!='check.py'})).encode()
            install="from pathlib import Path;import base64;p=Path("+repr(host)+");p.mkdir(parents=True,exist_ok=False);files="+repr({n:base64.b64encode(raw).decode() for n,raw in files.items()})+"\nfor n,v in files.items():\n q=p/n;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(base64.b64decode(v));q.chmod(0o644)"
            command=['set -eu','python3.12 -c '+shlex.quote(install),'chown -R jumpserve:jumpserve '+host,
                'systemd-run --wait --pipe --unit=jumpserve-builder-production-'+out.name.lower()+' --property=User=jumpserve --property=Group=jumpserve --property=EnvironmentFile=/etc/jumpserve-openclaw.env --property=NoNewPrivileges=true --property=PrivateTmp=true --property=ProtectHome=true --property=ProtectSystem=strict --property=ReadWritePaths=/var/lib/jumpserve-openclaw --property=MemoryMax=3G --property=RuntimeMaxSec=300 /opt/jumpserve/python/bin/python -B '+host+'/check.py']
            report['ssm']=r.ssm(command);report['host']=host
            (BASE/'native-command.json').write_text(json.dumps(report,indent=2)+'\n')
        else:
            original=json.loads((BASE/'native-command.json').read_bytes());call=original['ssm'];value=r.aws('ssm','get-command-invocation','--command-id',call['command_id'],'--instance-id',call['instance_id'])
            (out/'ssm-result.json').write_text(json.dumps(value,indent=2)+'\n');report['ssm_status']=value['Status']
            if value['Status'] in ('Pending','InProgress','Delayed'):report['status']='pending'
            else:
                assert value['Status']=='Success',value.get('StandardErrorContent','')[-2000:]
                result=next(json.loads(line) for line in value['StandardOutputContent'].splitlines() if line.startswith('{') and '"archive"' in line)
                item=result['archive'];assert item['path'].startswith('release-verification/experiment-builder-v2/') and item['sha256']==item['retrieved_sha256']
                key=r.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString']
                request=urllib.request.Request('https://regphejnlvfpyokpniny.supabase.co/storage/v1/object/research-workflow-raw/'+item['path'],headers={'apikey':key,'Authorization':'Bearer '+key})
                with r.prior.guard.OPEN.open(request,timeout=60) as response:raw=response.read(20000001)
                assert r.sha(raw)==item['sha256'];(out/'originals.zip').write_bytes(raw)
                with zipfile.ZipFile(io.BytesIO(raw)) as z:
                    for entry in json.loads(z.read('artifact-manifest.json')):assert r.sha(z.read(entry['path']))==entry['sha256']
                    control=json.loads(z.read('report.json'));assert control['status']=='passed' and control['live_provider_calls']==0
                    (out/'native-report.json').write_bytes(z.read('report.json'))
                report.update(archive=item,native_control='passed',live_provider_calls=0)
        if report['status']=='running':report['status']='complete'
    except Exception as error:report.update(status='failed',reason=str(error));raise
    finally:(out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(directory=str(out),**report),indent=2))
if __name__=='__main__':main()
