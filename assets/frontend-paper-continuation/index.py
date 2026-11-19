"""Wake the Next.js paper controller; no database or model work runs here."""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
import boto3

PATH = '/research-verification/api/paper-background'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def signature(key, timestamp, body):
    derived = hmac.new(key.encode(), b'jumpserve-paper-background-v1', hashlib.sha256).digest()
    return hmac.new(derived, (PATH+'\n'+timestamp+'\n'+body).encode(), hashlib.sha256).hexdigest()


def handler(event, context):
    # EventBridge cannot supply a URL, identity, model choice or arbitrary request.
    secret = json.loads(boto3.client('secretsmanager').get_secret_value(SecretId=os.environ['SECRET_ARN'])['SecretString'])
    key = secret.get('OPENAI_API_KEY')
    if not isinstance(key, str) or not key:
        raise RuntimeError('Paper continuation credentials unavailable.')
    body = '{"limit":2}'
    timestamp = str(int(time.time()))
    request = urllib.request.Request('https://jumpserve.quaint-lab.org'+PATH, data=body.encode(), method='POST', headers={
        'content-type': 'application/json', 'x-jumpserve-paper-timestamp': timestamp,
        'x-jumpserve-paper-signature': signature(key, timestamp, body),
    })
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=90) as response:
            if response.status != 200:
                raise RuntimeError('Paper continuation was not acknowledged.')
            payload = response.read(4097)
            if len(payload) > 4096:
                raise RuntimeError('Unexpected continuation response.')
            result = json.loads(payload)
            if result.get('version') != 'paper-background-v1':
                raise RuntimeError('Unexpected continuation version.')
            return {'advanced': result.get('advanced'), 'unavailable': result.get('unavailable')}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        # Never log request headers, credentials, response bodies or paper data.
        raise RuntimeError('Paper continuation temporarily unavailable; saved work will be reconciled.') from None
