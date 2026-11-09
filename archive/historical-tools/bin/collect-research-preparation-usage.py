"""Read-only, fixed-target bounded usage samples for the preparation release."""
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import boto3

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'docs/research-preparation-validation/production-usage-v1.json'
if DEST.exists():raise SystemExit('Preserve this capture; use a versioned follow-up.')
if os.sys.platform=='darwin':os.environ.setdefault('SSL_CERT_FILE','/etc/ssl/cert.pem')
first=json.loads((ROOT/'.test-artifacts/research-release/20261007T221548717353Z/production-server-report.json').read_text())
follow=json.loads((ROOT/'.test-artifacts/research-release/20261007T222058320533Z/production-server-report.json').read_text())
assert follow['passed'] and follow['targets']['aws_account']=='395567831870' and follow['targets']['supabase_project']=='regphejnlvfpyokpniny'
credentials=json.loads(subprocess.check_output(['aws','configure','export-credentials','--profile','jumpserve','--format','process'],timeout=20))
session=boto3.Session(aws_access_key_id=credentials['AccessKeyId'],aws_secret_access_key=credentials['SecretAccessKey'],aws_session_token=credentials['SessionToken'],region_name='us-east-1')
assert session.client('sts').get_caller_identity()['Account']=='395567831870'
start=int(dt.datetime.fromisoformat(first['started_at']).timestamp()*1000)
end=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
client=session.client('logs');groups=[]
for function in follow['checks'][0]['evidence']['functions']:
    group='/aws/lambda/'+function['name'];capture=dict(group=group,status='not-read',streams=[],report_samples=[],error_type=None)
    try:
        streams=client.describe_log_streams(logGroupName=group,orderBy='LastEventTime',descending=True,limit=3)['logStreams']
        for stream in streams:
            events=client.get_log_events(logGroupName=group,logStreamName=stream['logStreamName'],startTime=start,endTime=end,limit=200,startFromHead=True)['events']
            capture['streams'].append(dict(name=stream['logStreamName'],returned_events=len(events),pagination_exhausted=False))
            for event in events:
                message=event['message']
                if not message.startswith('REPORT RequestId:'):continue
                sample=dict(timestamp_epoch_ms=event['timestamp'],message=message)
                for key,pattern in [('duration_ms',r'\bDuration: ([0-9.]+) ms'),('billed_duration_ms',r'Billed Duration: ([0-9.]+) ms'),('memory_size_mb',r'Memory Size: ([0-9.]+) MB'),('max_memory_used_mb',r'Max Memory Used: ([0-9.]+) MB')]:
                    match=re.search(pattern,message);sample[key]=float(match.group(1)) if match else None
                capture['report_samples'].append(sample)
        capture['status']='sampled'
    except Exception as error:capture['status']='unavailable';capture['error_type']=type(error).__name__
    groups.append(capture)
runs=json.loads((ROOT/'.test-artifacts/research-release/20261007T222058320533Z/preparation-runs.json').read_text())
synthetic=first['checks'][2]['evidence']['artifacts'];prepared=follow['checks'][2]['evidence']['artifacts']
report=dict(version=1,created_at=dt.datetime.now(dt.timezone.utc).isoformat(),targets=follow['targets'],window=dict(start_epoch_ms=start,end_epoch_ms=end),bounds=dict(functions=2,streams_per_function=3,events_per_stream=200,pages_per_stream=1),cloudwatch=groups,run_usage=[dict(id=r['id'],requested_resources=r['requested_resources'],actual_resources=r['actual_resources'],usage=r['usage']) for r in runs],original_artifact_payload_bytes=sum(a['byte_count'] for a in synthetic+prepared),original_artifacts=18,experiment_ec2_requested=False,bedrock_evaluations_requested=False,measured_charges_usd=None,estimated_charges_usd=None,model_usage=None,unallocated_costs=['AWS Lambda/API/CloudWatch/asset storage','Supabase database/storage/egress','Amplify build/hosting','Codex and documentation retrieval'],limitations=['Bounded CloudWatch samples are not complete invocation accounting and can omit delayed events or older streams','Lambda memory reports describe the execution environment, not a measured per-job peak','Logical original payload bytes exclude database indexes, audit records, replicas and storage overhead','Preparation audit follow-up reused existing runs and made no production writes','Missing usage or charges are not zero'],documentation=['https://docs.aws.amazon.com/boto3/latest/reference/services/logs/client/describe_log_streams.html','https://docs.aws.amazon.com/boto3/latest/reference/services/logs/client/get_log_events.html'])
with DEST.open('x') as output:output.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(report=str(DEST),report_samples=sum(len(g['report_samples']) for g in groups),capture_statuses=[g['status'] for g in groups],original_payload_bytes=report['original_artifact_payload_bytes'],measured_charges_usd=None)))
