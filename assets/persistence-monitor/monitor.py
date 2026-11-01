"""Independent, read-only persistence probe. Never invokes workers or repairs."""
import json
import os
import re
import ssl
import time
import urllib.request

PROJECT = 'regphejnlvfpyokpniny'
NAMESPACE = 'JumpServe/Persistence'
URL = 'https://' + PROJECT + '.supabase.co/rest/v1/research_model_workers?select=id&limit=1'
_key = None
_key_until = 0


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Probe redirects are disabled.')


def probe(key, opener=None):
    if not isinstance(key, str) or not 20 <= len(key) <= 10000 or '\n' in key or '\r' in key:
        raise ValueError('Invalid probe credential.')
    if opener is None:
        context = ssl.create_default_context()
        context.keylog_filename = None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                                            urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request(URL, headers={'apikey': key, 'Authorization': 'Bearer ' + key})
    with opener.open(request, timeout=5) as response:
        raw = response.read(4097)
        if response.status != 200 or len(raw) > 4096:
            raise ValueError('Unconfirmed persistence probe.')
        rows = json.loads(raw)
        if not isinstance(rows, list) or len(rows) > 1 or any(row != {'id': 'openclaw-production-v1'} for row in rows):
            raise ValueError('Unexpected persistence projection.')


def handler(event, context):
    global _key, _key_until
    import boto3
    from botocore.config import Config
    config = Config(connect_timeout=2, read_timeout=3, retries={'total_max_attempts': 1})
    started = time.monotonic()
    reason = 'ready'
    success = 0
    try:
        arn = os.environ['SUPABASE_SECRET_ARN']
        if not re.fullmatch(r'arn:aws:secretsmanager:us-east-1:395567831870:secret:jumpserve/supabase-service-key(?:-[A-Za-z0-9]{6})?', arn):
            raise ValueError('Unexpected probe secret target.')
        if _key is None or time.monotonic() >= _key_until:
            _key = boto3.client('secretsmanager', config=config).get_secret_value(SecretId=arn)['SecretString']
            _key_until = time.monotonic() + 300
        probe(_key)
        success = 1
    except Exception:
        # HTTP errors can contain keys, SQL, or private data. Emit fixed metadata.
        _key = None
        _key_until = 0
        reason = 'persistence-unavailable'
    duration = round((time.monotonic() - started) * 1000, 2)
    dimensions = [{'Name': 'Project', 'Value': PROJECT}]
    boto3.client('cloudwatch', config=config).put_metric_data(Namespace=NAMESPACE, MetricData=[
        {'MetricName': 'DatabaseReachable', 'Dimensions': dimensions, 'Value': success, 'Unit': 'Count'},
        {'MetricName': 'DatabaseLatencyMs', 'Dimensions': dimensions, 'Value': duration, 'Unit': 'Milliseconds'},
    ])
    result = dict(version='persistence-probe-v1', reachable=bool(success), reason=reason, duration_ms=duration)
    print(json.dumps(result))
    return result
