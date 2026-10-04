"""Restore the existing deployed dependency layer for a scoped agent code release."""
import argparse
import hashlib
import io
import json
import ssl
from pathlib import Path
import urllib.request
import zipfile
import boto3

ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',default='jumpserve');a=p.parse_args()
    session=boto3.Session(profile_name=a.profile,region_name='us-east-1')
    if session.client('sts').get_caller_identity()['Account']!='395567831870':raise RuntimeError('Wrong AWS account')
    if json.loads((ROOT/'cdk.json').read_text())['context']['supabaseUrl']!='https://regphejnlvfpyokpniny.supabase.co':raise RuntimeError('Wrong Supabase project')
    cf=session.client('cloudformation');fn=cf.describe_stack_resource(StackName='JumpServeAgentStack',LogicalResourceId='AgentFnC1FD126F')['StackResourceDetail']['PhysicalResourceId']
    client=session.client('lambda');layers=client.get_function_configuration(FunctionName=fn)['Layers']
    if len(layers)!=1:raise RuntimeError('Unexpected dependency layer set')
    layer=client.get_layer_version_by_arn(Arn=layers[0]['Arn'])
    raw=urllib.request.urlopen(layer['Content']['Location'],timeout=60,context=ssl.create_default_context(cafile='/etc/ssl/cert.pem')).read()
    directory=ROOT/'agent/layer';directory.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for entry in archive.infolist():
            path=Path(entry.filename)
            if path.is_absolute() or '..' in path.parts:raise RuntimeError('Invalid layer path')
        archive.extractall(directory)
    record={'aws_account':'395567831870','layer_arn':layers[0]['Arn'],'zip_sha256':hashlib.sha256(raw).hexdigest(),'aws_code_sha256':layer['Content']['CodeSha256'],'purpose':'Reuse deployed dependencies without upgrading SDK for this release'}
    out=ROOT/'.test-artifacts';out.mkdir(exist_ok=True);(out/'http2-agent-layer.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
if __name__=='__main__':main()
