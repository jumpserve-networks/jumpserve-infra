"""Administer JumpServe prompt records using the Supabase Management API.

Uses SUPABASE_ACCESS_TOKEN or the existing macOS Supabase CLI login. Never prints
credentials. Publishing is performed by the Publish Agent Prompt workflow.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
PROJECT_REF = 'regphejnlvfpyokpniny'


def credential():
    token = os.environ.get('SUPABASE_ACCESS_TOKEN')
    if token:
        return token
    if sys.platform == 'darwin':
        for account in ('supabase', 'access-token'):
            result = subprocess.run(['security', 'find-generic-password', '-s', 'Supabase CLI',
                                     '-a', account, '-w'], capture_output=True, text=True)
            if result.returncode == 0:
                token = result.stdout.strip()
                if token.startswith('go-keyring-base64:'):
                    token = base64.b64decode(token.split(':', 1)[1]).decode()
                return token
    raise RuntimeError('Set SUPABASE_ACCESS_TOKEN or sign in with the Supabase CLI')


def query(sql, *, read_only=True):
    url = json.loads((ROOT / 'cdk.json').read_text())['context']['supabaseUrl']
    if url != f'https://{PROJECT_REF}.supabase.co':
        raise RuntimeError('Unexpected project; this command only administers JumpServe')
    request = urllib.request.Request(
        f'https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query',
        data=json.dumps({'query': sql, 'read_only': read_only}).encode(),
        headers={'Authorization': f'Bearer {credential()}', 'Content-Type': 'application/json'},
    )
    context = ssl.create_default_context(cafile='/etc/ssl/cert.pem' if sys.platform == 'darwin' else None)
    try:
        with urllib.request.urlopen(request, timeout=60, context=context) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Management errors may quote submitted SQL/prompt text; do not dump them.
        raise RuntimeError(f'Supabase request failed (HTTP {exc.code}); inspect the database operation') from None


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def migrate():
    schema = query("select column_name, data_type from information_schema.columns where table_schema='public' and table_name='agent_sessions'")
    columns = {row['column_name']: row['data_type'] for row in schema}
    if columns.get('id') != 'uuid' or columns.get('messages') != 'jsonb' or columns.get('user_id') != 'text':
        raise RuntimeError('Unexpected agent_sessions schema; migration aborted')
    exists = query("select to_regclass('public.agent_prompt_versions') is not null as present")[0]['present']
    if not exists:
        query((ROOT / 'database/202609200001_agent_prompts.sql').read_text(), read_only=False)
    seed = json.loads((ROOT / 'database/seed-agent-prompt.json').read_text())
    keys = ('id', 'version', 'system_prompt', 'research_context', 'created_by')
    values = ','.join(literal(seed[key]) for key in keys)
    query(f"insert into public.agent_prompt_versions ({','.join(keys)},updated_by) values ({values},{literal(seed['created_by'])}) on conflict (id) do nothing", read_only=False)
    return {'project': PROJECT_REF, 'seed_id': seed['id'], 'note': 'Seed is a draft until evaluated and published; existing prompts are preserved.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('migrate', help='Apply the additive schema and seed the existing prompt as a draft')
    commands.add_parser('list', help='List prompt metadata and the active version (no conversation data)')
    clone = commands.add_parser('draft', help='Copy a version into an editable draft')
    clone.add_argument('--from-id', type=UUID, required=True)
    clone.add_argument('--version', required=True)
    clone.add_argument('--actor', required=True)
    edit = commands.add_parser('edit', help='Update a draft from JSON, rejecting concurrent edits or published versions')
    edit.add_argument('--id', type=UUID, required=True)
    edit.add_argument('--file', type=Path, required=True)
    edit.add_argument('--expected-sha256', required=True)
    edit.add_argument('--actor', required=True)
    args = parser.parse_args()
    if args.command == 'migrate':
        result = migrate()
    elif args.command == 'list':
        result = query("select v.id, v.version, v.content_sha256, v.created_by, v.updated_by, v.updated_at, case when s.active_version_id=v.id then 'active' when v.published_at is not null then 'published' else 'draft' end as status from public.agent_prompt_versions v cross join public.agent_prompt_settings s order by v.created_at desc")
    elif args.command == 'edit':
        draft = json.loads(args.file.read_text())
        fields = ('version', 'system_prompt', 'research_context')
        if any(not isinstance(draft.get(field), str) or not draft[field].strip() for field in fields):
            raise RuntimeError('Draft JSON requires nonempty version, system_prompt and research_context strings')
        assignments = ','.join(f'{field}={literal(draft[field])}' for field in fields)
        result = query(f"update public.agent_prompt_versions set {assignments},updated_by={literal(args.actor)} where id={literal(args.id)}::uuid and published_at is null and content_sha256={literal(args.expected_sha256)} returning id,version,content_sha256", read_only=False)
        if not result:
            raise RuntimeError('Draft changed, is already published, or does not exist; no update made')
    else:
        result = query(f"insert into public.agent_prompt_versions (id,version,system_prompt,research_context,created_by,updated_by) select {literal(uuid4())}::uuid,{literal(args.version)},system_prompt,research_context,{literal(args.actor)},{literal(args.actor)} from public.agent_prompt_versions where id={literal(args.from_id)}::uuid returning id,version", read_only=False)
        if not result:
            raise RuntimeError('Source prompt version not found')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, urllib.error.URLError) as exc:
        raise SystemExit(str(exc)) from None
