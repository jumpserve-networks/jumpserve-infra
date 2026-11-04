"""Bounded Slack API reads for the trusted supervisor host adapter."""
import json
import re
import ssl
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('Slack redirects are disabled.')


def slack_call(token, method, **params):
    if method not in ('auth.test', 'conversations.members'):
        raise ValueError('Unexpected Slack adapter method.')
    context = ssl.create_default_context(); context.keylog_filename = None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=context))
    request = urllib.request.Request('https://slack.com/api/' + method,
        data=urllib.parse.urlencode(params).encode(), method='POST',
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/x-www-form-urlencoded'})
    with opener.open(request, timeout=20) as response:
        raw = response.read(1000001)
    if len(raw) > 1000000: raise ValueError('Slack response exceeds its bound.')
    value = json.loads(raw)
    if not value.get('ok'):
        code = value.get('error', '')
        raise ValueError('Slack read failed: ' + (code if re.fullmatch('[a-z_]{1,60}', code) else 'unknown'))
    return value
