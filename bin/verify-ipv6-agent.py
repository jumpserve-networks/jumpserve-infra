"""Read-only verification of the scoped JumpServe agent deployment and auth gate."""
import hashlib
import io
import json
from pathlib import Path
import ssl
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
import boto3

ROOT=Path(__file__).resolve().parents[1]
ACCOUNT='395567831870'
PROJECT='https://regphejnlvfpyokpniny.supabase.co'
URL='https://idk3jouyc6g2uolmge5ctuizwq0kpgcf.lambda-url.us-east-1.on.aws/'

def main():
    session=boto3.Session(profile_name='jumpserve',region_name='us-east-1')
    assert session.client('sts').get_caller_identity()['Account']==ACCOUNT,'Wrong AWS account'
    assert json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']==PROJECT,'Wrong project'
    resource=session.client('cloudformation').describe_stack_resource(StackName='JumpServeAgentStack',LogicalResourceId='AgentFnC1FD126F')
    fn=resource['StackResourceDetail']['PhysicalResourceId']
    client=session.client('lambda')
    config=client.get_function(FunctionName=fn)
    assert config['Configuration']['Environment']['Variables']['SUPABASE_URL']==PROJECT,'Deployed project differs'
    assert client.get_function_url_config(FunctionName=fn)['FunctionUrl']==URL,'Unexpected function URL'
    tls=ssl.create_default_context(cafile='/etc/ssl/cert.pem')
    raw=urllib.request.urlopen(config['Code']['Location'],timeout=60,context=tls).read()
    checks=[]
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for file in sorted((ROOT/'agent').rglob('*.py')):
            if any(part in ('layer','package','__pycache__') for part in file.relative_to(ROOT/'agent').parts):continue
            name=str(file.relative_to(ROOT/'agent'))
            expected=hashlib.sha256(file.read_bytes()).hexdigest()
            actual=hashlib.sha256(archive.read(name)).hexdigest()
            assert expected==actual,('Deployed code differs',name)
            checks.append(dict(path=name,sha256=actual))
    request=urllib.request.Request(URL,data=json.dumps({'action':'capabilities','module_id':'ipv6-dns-study'}).encode(),headers={'Content-Type':'application/json'})
    try:
        response=urllib.request.urlopen(request,timeout=30,context=tls)
        status=response.status;body=json.loads(response.read())
    except urllib.error.HTTPError as error:
        status=error.code;body=json.loads(error.read())
    assert status==401 and isinstance(body.get('error'),str),'Unauthenticated request was not rejected'
    report=dict(status='pass',checked_at=datetime.now(timezone.utc).isoformat(),aws_account=ACCOUNT,supabase_project='regphejnlvfpyokpniny',function=fn,function_url=URL,zip_sha256=hashlib.sha256(raw).hexdigest(),aws_code_sha256=config['Configuration']['CodeSha256'],code=checks,anonymous_request_status=status,layers=[row['Arn'] for row in config['Configuration']['Layers']],google_authenticated_chat='not exercised: no legitimate Google session available')
    directory=ROOT/'docs/ipv6-study-validation';directory.mkdir(exist_ok=True)
    assert not (directory/'agent-production-v1.json').exists(),'Preserve original verification'
    (directory/'agent-production-v1.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
