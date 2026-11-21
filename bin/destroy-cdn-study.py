"""Owner-authorized destruction of the 2026-08 CDN cache study resources.

Fixed AWS account, stack identities, bucket, and DNS names. Cloudflare and Fastly
are excluded by the owner's later instruction. No unrelated domain or stack is
accepted as input. Private receipts contain resource metadata, never credentials.
"""
import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.test-artifacts/cdn-study-destruction-20261120'
ACCOUNT = '395567831870'
PROJECT = 'jumpserve-cdn-cache-study'
BUCKET = 'jumpserve-cdn-origin-395567831870-us-east-1'
ZONE = 'Z00127102RO8M8IRXWKIG'
STACKS = {
    'jumpserve-cloudfront-exploratory': 'E199P1KDME1VNX',
    'jumpserve-cloudfront-do-origin': 'E1PLG78KNPCT3U',
    'jumpserve-cdn-origin': BUCKET,
}
DNS_NAMES = {
    'cloudfront.jumpserve.dev.', 'cloudfront-do.jumpserve.dev.', 'origin.jumpserve.dev.',
    '_c081f165c332f1c18a555e6690a781c1.cloudfront.jumpserve.dev.',
    '_0a1a9a92cc64783b52640fafe6f91544.cloudfront-do.jumpserve.dev.',
}

def aws(*args):
    result = subprocess.run(['aws', *args, '--profile', 'default', '--region', 'us-east-1',
        '--output', 'json', '--no-cli-pager', '--cli-connect-timeout', '10', '--cli-read-timeout', '30'],
        capture_output=True, text=True, timeout=60, env={**os.environ, 'AWS_MAX_ATTEMPTS': '1'})
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout) if result.stdout.strip() else {}

def save(name, value):
    OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(OUT / name, 'w', opener=lambda p, flags: os.open(p, flags, 0o600)) as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')

def original():
    return json.loads((OUT / 'aws-before.json').read_text())

def check_stack(name, stack, resources):
    assert name in STACKS and stack['StackName'] == name
    assert stack['StackId'].startswith('arn:aws:cloudformation:us-east-1:' + ACCOUNT + ':stack/' + name + '/')
    assert any(t['Key'] == 'project' and t['Value'] == PROJECT for t in stack.get('Tags', []))
    target_type = 'AWS::S3::Bucket' if name == 'jumpserve-cdn-origin' else 'AWS::CloudFront::Distribution'
    assert [r['PhysicalResourceId'] for r in resources if r['ResourceType'] == target_type] == [STACKS[name]]
    allowed = {'AWS::CloudFront::Distribution', 'AWS::CloudFront::CachePolicy',
        'AWS::CloudFront::ResponseHeadersPolicy', 'AWS::CertificateManager::Certificate',
        'AWS::Route53::RecordSet', 'AWS::S3::Bucket', 'AWS::S3::BucketPolicy'}
    assert all(r['ResourceType'] in allowed for r in resources), 'Unexpected resource in study stack'

def inventory():
    assert not (OUT / 'aws-before.json').exists(), 'Original inventory is immutable; use status'
    before = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'stacks': {}}
    for name in STACKS:
        stack = aws('cloudformation', 'describe-stacks', '--stack-name', name)['Stacks'][0]
        resources = aws('cloudformation', 'list-stack-resources', '--stack-name', name)['StackResourceSummaries']
        check_stack(name, stack, resources)
        template = aws('cloudformation', 'get-template', '--stack-name', name)['TemplateBody']
        before['stacks'][name] = {'stack': stack, 'resources': resources, 'template': template}
    tags = aws('s3api', 'get-bucket-tagging', '--bucket', BUCKET)['TagSet']
    assert any(t['Key'] == 'project' and t['Value'] == PROJECT for t in tags)
    before['bucket_tags'] = tags
    before['bucket_versioning'] = aws('s3api', 'get-bucket-versioning', '--bucket', BUCKET)
    before['dns'] = aws('route53', 'list-resource-record-sets', '--hosted-zone-id', ZONE)['ResourceRecordSets']
    before['distributions'] = aws('cloudfront', 'list-distributions')['DistributionList'].get('Items', [])
    # Keep metadata only; distribution origin headers could contain credentials.
    before['distributions'] = [{'id': d['Id'], 'aliases': d.get('Aliases', {}).get('Items', []),
        'origins': [o['DomainName'] for o in d['Origins']['Items']], 'enabled': d['Enabled']}
        for d in before['distributions']]
    save('aws-before.json', before)
    print(json.dumps({'inventoried_stacks': list(before['stacks']), 'bucket': BUCKET,
        'cloudflare_and_fastly': 'excluded_by_owner'}))

def delete_stacks():
    before = original()
    receipts = []
    for name, data in before['stacks'].items():
        identity = data['stack']['StackId']
        stack = aws('cloudformation', 'describe-stacks', '--stack-name', identity)['Stacks'][0]
        if stack['StackStatus'] in ('DELETE_IN_PROGRESS', 'DELETE_COMPLETE'):
            receipts.append({'stack': name, 'already_submitted': True, 'status': stack['StackStatus']})
            continue
        assert stack['StackStatus'] in ('CREATE_COMPLETE', 'UPDATE_COMPLETE')
        resources = aws('cloudformation', 'list-stack-resources', '--stack-name', identity)['StackResourceSummaries']
        check_stack(name, stack, resources)
        token = 'owner-destroy-cdn-study-20261120-' + name
        save(name + '-delete-intent.json', {'stack_id': identity, 'client_request_token': token})
        aws('cloudformation', 'delete-stack', '--stack-name', identity, '--client-request-token', token)
        receipts.append({'stack': name, 'deletion_submitted': True})
        save('stack-deletions.json', receipts)
    print(json.dumps(receipts))

def purge_bucket():
    before = original()
    assert before['stacks']['jumpserve-cdn-origin']['stack']['StackName'] == 'jumpserve-cdn-origin'
    state = aws('cloudformation', 'describe-stacks', '--stack-name', before['stacks']['jumpserve-cdn-origin']['stack']['StackId'])['Stacks'][0]['StackStatus']
    assert state == 'DELETE_COMPLETE', 'Finish the origin stack removal before purging its retained bucket'
    tags = aws('s3api', 'get-bucket-tagging', '--bucket', BUCKET)['TagSet']
    assert any(t['Key'] == 'project' and t['Value'] == PROJECT for t in tags)
    # Empty every object version, including delete markers, in bounded batches.
    removed = 0
    for _ in range(1000):
        page = aws('s3api', 'list-object-versions', '--bucket', BUCKET, '--max-keys', '1000', '--no-paginate')
        objects = [{'Key': o['Key'], 'VersionId': o['VersionId']}
            for field in ('Versions', 'DeleteMarkers') for o in page.get(field, [])]
        if not objects: break
        result = aws('s3api', 'delete-objects', '--bucket', BUCKET,
            '--delete', json.dumps({'Objects': objects, 'Quiet': True}))
        assert not result.get('Errors'), result.get('Errors')
        removed += len(objects)
        save('bucket-purge-progress.json', {'deleted_object_versions': removed})
    else: raise RuntimeError('Bounded bucket purge requires reconciliation')
    remaining = aws('s3api', 'list-objects-v2', '--bucket', BUCKET, '--max-keys', '1')
    assert not remaining.get('Contents'), 'Unversioned object remains'
    uploads = aws('s3api', 'list-multipart-uploads', '--bucket', BUCKET).get('Uploads', [])
    for upload in uploads:
        aws('s3api', 'abort-multipart-upload', '--bucket', BUCKET, '--key', upload['Key'], '--upload-id', upload['UploadId'])
    # CloudFormation intentionally retains this bucket. User explicitly approved
    # permanent experiment destruction, so remove the now-empty bucket directly.
    aws('s3api', 'delete-bucket', '--bucket', BUCKET, '--expected-bucket-owner', ACCOUNT)
    save('bucket-deleted.json', {'bucket': BUCKET, 'deleted_object_versions': removed,
        'multipart_uploads_aborted': len(uploads), 'deleted_at': dt.datetime.now(dt.timezone.utc).isoformat()})
    print(json.dumps({'bucket_deleted': BUCKET, 'object_versions_deleted': removed}))

def clean_dns():
    before = original()
    for data in before['stacks'].values():
        assert aws('cloudformation', 'describe-stacks', '--stack-name', data['stack']['StackId'])['Stacks'][0]['StackStatus'] == 'DELETE_COMPLETE', 'Finish stack removals before deleting residual DNS'
    current = aws('route53', 'list-resource-record-sets', '--hosted-zone-id', ZONE)['ResourceRecordSets']
    previous = {r['Name']: r for r in before['dns'] if r['Name'] in DNS_NAMES}
    removals = [r for r in current if r['Name'] in DNS_NAMES]
    assert all(r == previous[r['Name']] for r in removals), 'DNS changed after inventory'
    if removals:
        batch = {'Comment': 'Owner-directed CDN study destruction; Fastly records excluded',
            'Changes': [{'Action': 'DELETE', 'ResourceRecordSet': r} for r in removals]}
        change = aws('route53', 'change-resource-record-sets', '--hosted-zone-id', ZONE, '--change-batch', json.dumps(batch))
    else: change = {}
    save('dns-deleted.json', {'names': [r['Name'] for r in removals], 'change': change})
    print(json.dumps({'deleted_dns_names': [r['Name'] for r in removals]}))

def status():
    result = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'stacks': {}}
    for name, data in original()['stacks'].items():
        stack = aws('cloudformation', 'describe-stacks', '--stack-name', data['stack']['StackId'])['Stacks'][0]
        result['stacks'][name] = stack['StackStatus']
        if stack['StackStatus'] == 'DELETE_FAILED':
            result[name + '_failures'] = [e for e in aws('cloudformation', 'describe-stack-events', '--stack-name', data['stack']['StackId'])['StackEvents'] if e['ResourceStatus'] == 'DELETE_FAILED']
    result['remaining_distributions'] = [{'id': d['Id'], 'enabled': d['Enabled']}
        for d in aws('cloudfront', 'list-distributions')['DistributionList'].get('Items', [])
        if d['Id'] in STACKS.values()]
    save('aws-status.json', result)
    print(json.dumps(result))

def read_public_page(path):
    # Use the system TLS client, including its normal certificate verification.
    # A framework Python install may not have the machine's CA bundle installed.
    raw = subprocess.check_output(['curl', '--fail', '--silent', '--show-error', '--max-time', '30',
        '--write-out', '\n%{http_code}', 'https://jumpserve.quaint-lab.org' + path], timeout=35)
    body, status_code = raw.decode().rsplit('\n', 1)
    assert status_code == '200', 'Public page did not return HTTP 200'
    assert '<html' in body and 'Application error: a server-side exception' not in body
    if path != '/': assert 'Shared local assessment' in body
    return {'path': path, 'status': int(status_code)}

def verify():
    before = original()
    result = {'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'stacks': {},
        'excluded_by_owner': ['Cloudflare', 'Fastly']}
    for name, data in before['stacks'].items():
        state = aws('cloudformation', 'describe-stacks', '--stack-name', data['stack']['StackId'])['Stacks'][0]['StackStatus']
        assert state == 'DELETE_COMPLETE', (name, state)
        result['stacks'][name] = state
    buckets = aws('s3api', 'list-buckets', '--query', 'Buckets[].Name')
    assert BUCKET not in buckets, 'Study origin bucket still exists'
    current = aws('cloudfront', 'list-distributions')['DistributionList'].get('Items', [])
    ids = {d['Id'] for d in current}
    assert not ids & set(STACKS.values()), 'Study distribution remains'
    original_other = {d['id']: d for d in before['distributions'] if d['id'] not in STACKS.values()}
    other = {d['Id']: {'id': d['Id'], 'aliases': d.get('Aliases', {}).get('Items', []),
        'origins': [o['DomainName'] for o in d['Origins']['Items']], 'enabled': d['Enabled']}
        for d in current if d['Id'] in original_other}
    assert other == original_other, 'Unrelated CDN distribution changed'
    records = aws('route53', 'list-resource-record-sets', '--hosted-zone-id', ZONE)['ResourceRecordSets']
    assert not {r['Name'] for r in records} & DNS_NAMES, 'Study DNS record remains'
    key = lambda r: (r['Name'], r['Type'])
    preserved = {key(r): r for r in before['dns'] if r['Name'] not in DNS_NAMES}
    assert {key(r): r for r in records if key(r) in preserved} == preserved, 'Excluded Fastly or zone DNS changed'
    certificates = set(aws('acm', 'list-certificates', '--query', 'CertificateSummaryList[].CertificateArn'))
    study_certificates = {r['PhysicalResourceId'] for data in before['stacks'].values() for r in data['resources'] if r['ResourceType'] == 'AWS::CertificateManager::Certificate'}
    assert not certificates & study_certificates, 'Study certificate remains'
    for resource_type, operation, query in (
            ('AWS::CloudFront::CachePolicy', 'list-cache-policies', 'CachePolicyList.Items[].CachePolicy.Id'),
            ('AWS::CloudFront::ResponseHeadersPolicy', 'list-response-headers-policies', 'ResponseHeadersPolicyList.Items[].ResponseHeadersPolicy.Id')):
        expected = {r['PhysicalResourceId'] for data in before['stacks'].values() for r in data['resources'] if r['ResourceType'] == resource_type}
        remaining = set(aws('cloudfront', operation, '--type', 'custom', '--query', query) or [])
        assert not expected & remaining, 'Study CloudFront policy remains'
    dns_receipt = json.loads((OUT / 'dns-deleted.json').read_text())
    change_id = dns_receipt.get('change', {}).get('ChangeInfo', {}).get('Id')
    if change_id: assert aws('route53', 'get-change', '--id', change_id)['ChangeInfo']['Status'] == 'INSYNC', 'DNS change still propagating'
    # Verify the origin and its orphaned resources in the original DO context.
    checks = [('droplet', ['compute', 'droplet', 'get', '595750731']),
        ('firewall', ['compute', 'firewall', 'get', '9d46dd7f-30d7-4aca-a0a8-ca1416fa89bd']),
        ('ssh_key', ['compute', 'ssh-key', 'get', '58860099']),
        ('tag', ['compute', 'tag', 'get', 'jumpserve-neutral-origin'])]
    result['digitalocean'] = {}
    for label, args in checks:
        check = subprocess.run(['doctl', '--http-retry-max', '0', '--context', 'jumpserve-origin', *args, '--output', 'json'], capture_output=True, text=True, timeout=30)
        assert check.returncode != 0 and re.search(r': 404(?:\s|\()', check.stderr + check.stdout), label + ' absence unverified'
        result['digitalocean'][label] = 'not_found_404'
    snapshots = subprocess.check_output(['doctl', '--http-retry-max', '0', '--context', 'jumpserve-origin',
        'compute', 'snapshot', 'list', '--resource', 'droplet', '--output', 'json'], timeout=30)
    assert not [s for s in json.loads(snapshots) if str(s.get('resource_id')) == '595750731'], 'DO origin snapshot remains'
    result['public_http'] = []
    for path in ('/', '/research-verification/assessment/b702bf86-5b1e-42d4-8262-f4183d6da4fc'):
        result['public_http'].append(read_public_page(path))
    result.update(passed=True, bucket_deleted=True, distributions_deleted=2, certificates_deleted=len(study_certificates),
        unrelated_distributions_preserved=len(other), fastly_dns_preserved=True)
    save('verification.json', result)
    print(json.dumps(result))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['inventory', 'delete-stacks', 'purge-bucket', 'clean-dns', 'status', 'verify'])
    args = parser.parse_args()
    assert aws('sts', 'get-caller-identity')['Account'] == ACCOUNT, 'Wrong AWS account'
    {'inventory': inventory, 'delete-stacks': delete_stacks, 'purge-bucket': purge_bucket,
        'clean-dns': clean_dns, 'status': status, 'verify': verify}[args.mode]()
