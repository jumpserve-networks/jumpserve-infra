"""Fixed-target read-only evidence collection for the legitimate-user pilot.

No token inputs, writes, model calls, queue submissions or EC2 mutations. The
application's production UI performs authenticated mutations and actual reviews.
"""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('claim_live_release', ROOT / 'bin/claim-design-release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
BASE = ROOT / '.test-artifacts/claim-flow/v1'
ORIGINAL_STUDY = 'a0c13133-7f02-5aae-93d0-43fb1332e0ad'
ORIGINAL_CLAIM = '40b409cc-3aec-5fb9-a47e-b8d7fdecd072'


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inspect', 'observe'))
    args = parser.parse_args()
    directory = BASE / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True, exist_ok=False)
    os.chmod(directory, 0o700)
    result = dict(mode=args.mode, started_at=stamp(), status='running', read_only=True,
                  collector=dict(identity='Primary Codex AI implementer', type='AI', independent=False),
                  new_model_calls_by_collector=0, new_instances_by_collector=0, measured_charges_usd=None)
    try:
        result['targets'] = release.guard.target()
        result['protocol_sha256'] = sha((ROOT / 'docs/claim-design-authenticated-verification-protocol-v1.md').read_bytes())
        if args.mode == 'inspect':
            result['existing_contexts'] = release.admin.query("select count(*) count from research_claim_designs where document->'study'->>'id'=" + release.admin.literal(ORIGINAL_STUDY) + " and document->'claim'->>'id'=" + release.admin.literal(ORIGINAL_CLAIM))
            result['active_prompt'] = release.active()
            result['source_manifest'] = release.queue.source()
        else:
            identity = json.loads((BASE / 'identity.json').read_text())
            study = identity['study_id']
            import uuid
            uuid.UUID(study)
            contexts = release.admin.query('select study_id,document,raw_document,sha256,source_id,claim_id from research_claim_designs where study_id=' + release.admin.literal(study) + '::uuid')
            if len(contexts) != 1 or contexts[0]['document']['study']['id'] != ORIGINAL_STUDY or contexts[0]['document']['claim']['id'] != ORIGINAL_CLAIM:
                raise RuntimeError('Only the declared source-bound pilot can be inspected')
            sys.path.insert(0, str(ROOT.parent / 'jumpserve-back-end/research_workflow'))
            import store
            os.environ.update(SUPABASE_URL='https://regphejnlvfpyokpniny.supabase.co',
                              SUPABASE_SERVICE_ROLE_KEY=release.aws('secretsmanager', 'get-secret-value', '--secret-id', 'jumpserve/supabase-service-key')['SecretString'],
                              SUPABASE_ANON_KEY=json.loads((ROOT / 'cdk.json').read_text())['context']['supabaseAnonKey'],
                              SSL_CERT_FILE='/etc/ssl/cert.pem')
            result['study_id'] = study
            result['claim_context_sha256'] = contexts[0]['sha256']
            definition = release.admin.query("select pg_get_functiondef('public.research_save_idea_packet(uuid,uuid,uuid,uuid,jsonb,text,text,text)'::regprocedure) definition")[0]['definition']
            (directory / 'save-packet-catalog-definition.sql').write_text(definition)
            result['deployed_duplicate_guard'] = dict(catalog_definition_sha256=sha(definition.encode()),
                unchanged_packet_guard_present='latest.document IS NOT DISTINCT FROM p_document'.lower() in definition.lower(),
                provenance='PostgreSQL catalog representation; not originally executed migration bytes')
            kinds = ('idea_packets', 'idea_runs', 'idea_readiness', 'idea_campaign_links', 'protocols', 'campaigns', 'queue_jobs', 'runs', 'measurements', 'artifacts', 'assessments')
            records = {}
            for kind in kinds:
                records[kind] = store.rows(kind, {'study_id': 'eq.' + study, 'limit': 100})
            raw = json.dumps(records, indent=2).encode() + b'\n'
            path = directory / 'private-records.json'
            path.write_bytes(raw)
            path.chmod(0o600)
            result['private_records'] = dict(sha256=sha(raw), bytes=len(raw), counts={k: len(v) for k, v in records.items()})
            result['queue'] = [{k: row.get(k) for k in ('id', 'status', 'reason', 'definition_sha256', 'run_id', 'created_at', 'updated_at')} for row in records['queue_jobs']]
            result['measurements'] = [{k: row.get(k) for k in ('id', 'run_id', 'observation_id', 'configuration_identity', 'metric', 'units', 'value', 'status', 'reason')} for row in records['measurements']]
            result['model_attempts'] = [{k: row.get(k) for k in ('id', 'packet_id', 'task', 'status', 'reason', 'prompt_version_id', 'model_id', 'usage')} for row in records['idea_runs']]
            originals = []
            for row in records['artifacts']:
                raw = store.artifact_bytes(study, row['id'], maximum=10_000_000)
                path = directory / ('original-' + row['sha256'])
                path.write_bytes(raw)
                path.chmod(0o600)
                try:
                    store.request('/storage/v1/object/' + store.BUCKET + '/' + row['storage_path'], public=True, raw=True)
                except store.StoreError as error:
                    if not any('HTTP ' + str(status) in str(error) for status in (400, 401, 403, 404)):
                        raise
                    anonymous_denied = True
                else:
                    raise RuntimeError('Private owner artifact was readable anonymously')
                originals.append(dict(id=row['id'], sha256=sha(raw), bytes=len(raw), retrieval_hash_verified=True,
                                      anonymous_read_denied=anonymous_denied, provenance=row['provenance']))
            result['originals'] = originals
        result['status'] = 'complete'
    except Exception as error:
        result.update(status='failed', reason=str(error))
        raise
    finally:
        result['ended_at'] = stamp()
        path = directory / 'receipt.json'
        path.write_text(json.dumps(result, indent=2) + '\n')
        path.chmod(0o600)
        print(json.dumps(dict(directory=str(directory), mode=args.mode, status=result['status'], reason=result.get('reason'))))


if __name__ == '__main__':
    main()
