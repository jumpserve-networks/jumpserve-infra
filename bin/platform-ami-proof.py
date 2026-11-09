"""Verify the actual selected benchmark AMI before issuing a release receipt."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import uuid

def aws(*args):return json.loads(subprocess.check_output(['aws',*args,'--region','us-east-1','--output','json'],timeout=30))

def main():
    manifest=json.loads(Path('cdk.out/benchmark-ami.json').read_bytes())
    operation=str(uuid.UUID(os.environ['PLATFORM_OPERATION_ID']))
    revision=os.environ['BACKEND_COMMIT']
    if manifest['backend_commit']!=revision:raise ValueError('AMI manifest revision differs.')
    function='JumpServeBenchmarkStack-LaunchBenchmarkFn5833EFAD-L6HWyzv2tgwl'
    env=aws('lambda','get-function-configuration','--function-name',function)['Environment']['Variables']
    image=aws('ec2','describe-images','--image-ids',manifest['ami_id'])['Images'][0]
    tags={t['Key']:t['Value'] for t in image.get('Tags',[])}
    # Read both the active launcher and the image's recorded source identity.
    if env['AMI_ID']!=manifest['ami_id'] or env['BENCHMARK_IMAGE_MODE']!='prebaked' or image['State']!='available' or tags.get('BackendCommit')!=revision:raise ValueError('The verified source/image is not selected in production.')
    candidate=json.loads(Path('cdk.out/benchmark-ami-verification.json').read_bytes())
    live=json.loads(Path('cdk.out/benchmark-ami-live-verification.json').read_bytes())
    for reports,statuses,label in [(candidate,{'completed','failed'},'Candidate'),(live,{'completed'},'Live')]:
        if (not isinstance(reports,list) or len(reports)!=len(statuses)
                or any(not isinstance(row,dict) for row in reports)
                or {row.get('status') for row in reports}!=statuses
                or any(row.get('backendCommit')!=revision or row.get('amiId')!=manifest['ami_id'] for row in reports)
                or not next(row for row in reports if row['status']=='completed').get('parentRunId')):
            raise ValueError(label+' verification is not bound to this image, source and persisted successful parent run.')
    proof=dict(version='platform-production-verification-v1',passed=True,operation_id=operation,component='backend',repository='jumpserve-networks/jumpserve-back-end',revision=revision,verified_at=dt.datetime.now(dt.timezone.utc).isoformat(),evidence=dict(ami_id=manifest['ami_id'],function=function,candidate_verification=candidate,live_verification=live,image_tags=tags))
    Path('production-verification.json').write_text(json.dumps(proof,sort_keys=True)+'\n')

if __name__=='__main__':main()
