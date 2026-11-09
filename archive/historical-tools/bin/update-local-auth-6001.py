"""Register JumpServe's port-6001 local OAuth callback on its fixed project.

Only the redirect allowlist is updated. Receipts contain public origins only;
provider secrets and the Management API credential never leave memory.
"""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import ssl
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PROJECT = 'regphejnlvfpyokpniny'
SITE = 'https://jumpserve.quaint-lab.org'
CALLBACKS = ('http://localhost:6001/auth/callback', 'http://localhost:6001/auth/callback*')
OUT = ROOT.parent / 'jumpserve-front-end/.test-artifacts/local-port-6001'


def main():
    if len(sys.argv) != 1:
        raise ValueError('This command only registers the two fixed JumpServe local callbacks.')
    configured = json.loads((ROOT / 'cdk.json').read_text())['context']['supabaseUrl']
    expected = 'https://' + PROJECT + '.supabase.co'
    frontend = ROOT.parent / 'jumpserve-front-end/.env.local'
    values = dict(line.split('=', 1) for line in frontend.read_text().splitlines()
                  if line.startswith(('NEXT_PUBLIC_SUPABASE_URL=', 'NEXT_PUBLIC_SITE_URL=')))
    if configured != expected or values.get('NEXT_PUBLIC_SUPABASE_URL', '').strip().strip('\"\'') != expected:
        raise RuntimeError('JumpServe project identity differs; no auth settings changed.')
    if values.get('NEXT_PUBLIC_SITE_URL', '').strip().strip('\"\'') != 'http://localhost:6001':
        raise RuntimeError('Local app origin differs; no auth settings changed.')
    spec = importlib.util.spec_from_file_location('admin', ROOT / 'bin/agent-prompts.py')
    admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(admin)
    if admin.PROJECT_REF != PROJECT:
        raise RuntimeError('Credential helper targets another project.')
    credential = admin.credential()
    endpoint = 'https://api.supabase.com/v1/projects/' + PROJECT + '/config/auth'
    context = ssl.create_default_context(cafile='/etc/ssl/cert.pem' if sys.platform == 'darwin' else None)

    def request(method='GET', body=None):
        req = urllib.request.Request(endpoint, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'Bearer ' + credential, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=20, context=context) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError('Supabase Auth request failed (HTTP ' + str(error.code) + ').') from None

    original = request()
    if original.get('site_url') != SITE or not isinstance(original.get('uri_allow_list'), str):
        raise RuntimeError('JumpServe Auth identity or allowlist differs; no settings changed.')
    existing = original['uri_allow_list']
    patterns = [value.strip() for value in existing.split(',') if value.strip()]
    additions = [value for value in CALLBACKS if value not in patterns]
    updated = existing + (',' if existing else '') + ','.join(additions) if additions else existing
    receipt = dict(project=PROJECT,site_url=SITE,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        before=patterns,planned_additions=additions,status='prepared',aws_resources_used=False,
        scope='Register the precise local app callback; retain the production site and existing redirects.')
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    before_path = OUT / ('auth-redirect-' + stamp + '-before.json')
    with before_path.open('x') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    if additions:
        current = request()
        if current.get('site_url') != SITE or current.get('uri_allow_list') != existing:
            raise RuntimeError('Redirect settings changed during preparation; inspect before retrying.')
        request('PATCH', {'uri_allow_list': updated})
    final = request()
    if final.get('site_url') != SITE or final.get('uri_allow_list') != updated:
        raise RuntimeError('Redirect update could not be verified; inspect the retained receipt.')
    receipt.update(status='verified',changed=bool(additions),after=[v.strip() for v in updated.split(',') if v.strip()],
        finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        google_provider_round_trip='Not exercised; no legitimate browser session used.')
    with (OUT / ('auth-redirect-' + stamp + '-after.json')).open('x') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, urllib.error.URLError) as error:
        raise SystemExit(str(error)) from None
