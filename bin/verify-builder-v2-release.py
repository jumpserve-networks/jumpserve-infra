"""Fixed-target builder production smoke and evidence retrieval; no inference."""
import argparse,base64,datetime as dt,importlib.util,io,json,pathlib,shlex,urllib.request,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/builder-production-v2'
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['native','collect-native']);args=parser.parse_args()
    BASE.mkdir(parents=True,exist_ok=True);out=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir()
    report=dict(protocol='experiment-builder-production-v2',mode=args.mode,status='running',targets=r.target(),measured_charges_usd=None)
    try:
        if args.mode=='native':
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
