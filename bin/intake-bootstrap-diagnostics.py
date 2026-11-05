#!/usr/bin/env python3
"""Read-only startup diagnostics for the deployed dedicated intake host."""
import base64
import json
import re
import time
from pathlib import Path

import boto3
from botocore.config import Config

INSTANCE = 'i-00dc52abbcf706670'
REGION = 'us-east-1'
OUT = Path('.test-artifacts/intake-bootstrap')
# No environment, auth stores, parameter values, prompts, or paper text are read.
COMMAND = r'''set -eu
systemctl show jumpserve-intake.service --property=LoadState,ActiveState,SubState,Result,NRestarts,ExecMainStatus
cloud-init status --format json || true
python3 - <<'PY'
import json, pathlib
names=['/opt/jumpserve/dependencies/install.sh','/opt/jumpserve/node/bin/node','/opt/jumpserve/openclaw/node_modules/openclaw/package.json','/opt/jumpserve/python/bin/python','/opt/jumpserve/intake-runtime/intake-manifest.json','/etc/jumpserve-intake.env','/etc/systemd/system/jumpserve-intake.service']
print(json.dumps({'installed_paths': {n:pathlib.Path(n).exists() for n in names}}))
PY
tail -n 70 /var/log/cloud-init-output.log
journalctl -u jumpserve-intake.service -n 70 --no-pager -o cat
'''


def redact(value):
    value = re.sub(r'(?i)(bearer\s+)[^\s\"\']+', r'\1[redacted]', value)
    value = re.sub(r'(?i)((?:access_token|refresh_token|authorization|api_key|secret_access_key)[\"\s:=]+)[^\s,}\"\']+', r'\1[redacted]', value)
    value = re.sub(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\b(?:sk-|xapp-|xoxb-)[A-Za-z0-9_-]+', '[redacted]', value)
    return re.sub(r'[A-Za-z0-9_+/=-]{96,}', '[redacted-long-value]', value)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    config = Config(region_name=REGION, retries={'total_max_attempts': 1})
    def client(name):
        return boto3.client(name, config=config)
    assert client('sts').get_caller_identity()['Account'] == '395567831870', 'Wrong AWS account'
    ec2, ssm = client('ec2'), client('ssm')
    instance = ec2.describe_instances(InstanceIds=[INSTANCE])['Reservations'][0]['Instances'][0]
    tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}
    assert tags.get('aws:cloudformation:stack-name') == 'JumpServeIntakeStack', 'Wrong host stack'
    info = ssm.describe_instance_information(Filters=[{'Key': 'InstanceIds', 'Values': [INSTANCE]}])['InstanceInformationList']
    report = {'instance_id': INSTANCE, 'state': instance['State']['Name'], 'type': instance['InstanceType'],
              'public_ip_assigned': bool(instance.get('PublicIpAddress')), 'ssm_ping': info[0]['PingStatus'] if info else None}
    console = ec2.get_console_output(InstanceId=INSTANCE, Latest=True)
    console_text = console.get('Output', '')
    if console_text and '\n' not in console_text:
        try:
            console_text = base64.b64decode(console_text, validate=True).decode('utf-8')
        except (ValueError, UnicodeDecodeError):
            pass
    (OUT / 'console.txt').write_text(redact(console_text))
    if info and info[0]['PingStatus'] == 'Online':
        result = ssm.send_command(InstanceIds=[INSTANCE], DocumentName='AWS-RunShellScript',
            Comment='Read-only dedicated intake bootstrap diagnostics', TimeoutSeconds=120,
            Parameters={'commands': [COMMAND], 'executionTimeout': ['90']})
        report['command_id'] = result['Command']['CommandId']
        (OUT / 'receipt.json').write_text(json.dumps(report))
        for _ in range(60):
            time.sleep(2)
            try:
                result = ssm.get_command_invocation(CommandId=report['command_id'], InstanceId=INSTANCE)
            except ssm.exceptions.InvocationDoesNotExist:
                continue
            if result['Status'] in ('Pending', 'InProgress', 'Delayed'):
                continue
            report.update(command_status=result['Status'], response_code=result['ResponseCode'])
            (OUT / 'startup.txt').write_text(redact(result.get('StandardOutputContent', '') + '\n' + result.get('StandardErrorContent', '')))
            break
        else:
            report['command_status'] = 'unconfirmed'
    (OUT / 'receipt.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


if __name__ == '__main__':
    main()
