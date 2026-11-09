"""Fixed-target catalog release: no arbitrary commands, SQL, URLs or assessment inputs."""
import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import unicodedata
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('catalog_prior', ROOT / 'bin/public-queue-release.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
r = p.r
BACKEND = 'a94eb0e26c96da73aa4d7d435899b2ce796db61d'
PROTOCOL = 'assessment-catalog-production-release-v1'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
stamp = lambda: dt.datetime.now(dt.timezone.utc).isoformat()
encoded = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
IDS = "'e79f5cab-d28f-4cea-bf0c-3407933c8cfd','5ef8e6bd-e3ff-4ba9-8427-d25fb525fb74','584e6ce7-b104-4f77-aa3a-2a2c0eac0f31'"
CATALOG_SQL = """select s.id::text,s.title,s.created_at::text,s.paper_upload,
 w.status workflow_status,coalesce(p.status='published',false) published
 from research_studies s left join research_autonomy_workflows w on w.study_id=s.id
 left join lateral (select status from research_publications where study_id=s.id order by version desc limit 1) p on true
 where s.study_kind='paper' order by s.created_at desc,s.id desc limit 1001"""


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def identities():
    rows = r.admin.query("select s.id::text,s.title,s.paper_upload,w.initial_sha256 from research_studies s left join research_autonomy_workflows w on w.study_id=s.id where s.id in (" + IDS + ") order by s.id")
    require(len(rows) == 3, 'Retained assessment identities are missing.')
    return dict(retained_metadata_sha256=sha(encoded(rows)), prompts=r.prior.pointers())


def clean(value):
    # Independent normalization; the production title parser is not imported.
    text = unicodedata.normalize('NFKC', str(value or '')).replace('\u00ad', '')
    return ' '.join(''.join(' ' if unicodedata.category(c).startswith('C') else c for c in text).split()).casefold()


def seeded(row):
    upload = row.get('paper_upload')
    name = upload.get('filename') if isinstance(upload, dict) else None
    return isinstance(name, str) and clean(row['title']) in (clean(name), clean(name[:-4]), 'uploaded paper')


def instant(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def catalog(directory, attempts):
    for attempt in range(1, 4):
        entry = dict(attempt=attempt, status='running', pages=[])
        attempts.append(entry)
        before = r.admin.query(CATALOG_SQL)
        observed, seen, cursor = [], set(), None
        try:
            for page in range(1, 101):
                code, raw = p.request('/papers' + ('?before=' + urllib.parse.quote(cursor, safe='') if cursor else ''))
                (directory / f'catalog-attempt-{attempt}-page-{page}.json').write_bytes(raw)
                entry['pages'].append(dict(page=page, status=code, bytes=len(raw), sha256=sha(raw)))
                require(code == 200 and len(raw) <= 200_000, 'Catalog status or response bound differs.')
                data = json.loads(raw)
                require(set(data) == {'version', 'access', 'papers', 'coverage', 'next_cursor'}, 'Catalog envelope includes unexpected fields.')
                require(data['version'] == 'research-paper-catalog-v1' and data['access'] == 'public-read-only', 'Catalog version/access differs.')
                require(isinstance(data['papers'], list) and len(data['papers']) <= 10, 'Catalog page bound differs.')
                require(data['coverage'] == dict(papers=len(data['papers'])), 'Catalog coverage differs.')
                for row in data['papers']:
                    require(set(row) == {'id', 'title', 'created_at', 'workflow_status', 'published'}, 'Catalog includes private/unexpected fields.')
                    require(str(uuid.UUID(row['id'])) == row['id'] and row['id'] not in seen, 'Duplicate/invalid assessment identity.')
                    require(type(row['published']) is bool, 'Publication flag is not boolean.')
                    seen.add(row['id'])
                    observed.append(row)
                cursor = data['next_cursor']
                if cursor is None:
                    break
                require(isinstance(cursor, str) and 0 < len(cursor) <= 256 and data['papers'], 'Invalid paging continuation.')
            require(cursor is None, 'Catalog exceeds the declared 100-page budget.')
            after = r.admin.query(CATALOG_SQL)
            entry.update(database_before_sha256=sha(encoded(before)), database_after_sha256=sha(encoded(after)))
            if before != after:
                entry.update(status='excluded-concurrent-change', reason='Independent observations changed during paging; original pages retained.')
                continue
            require(len(before) <= 1000 and len(observed) == len(before), 'Catalog/database counts differ or exceed the budget.')
            for actual, expected in zip(observed, before):
                require(actual['id'] == expected['id'] and instant(actual['created_at']) == instant(expected['created_at']), 'Catalog identity/order/epoch differs.')
                require(actual['workflow_status'] == expected['workflow_status'] and actual['published'] == expected['published'], 'Catalog status/publication differs.')
                require(actual['title'] == (None if seeded(expected) else expected['title']), 'Catalog title projection differs.')
            entry.update(status='passed', assessments=len(observed), published=sum(x['published'] for x in observed), unpublished=sum(not x['published'] for x in observed), title_check_assumption='Independent normalization and filename classification; shared retained metadata inputs.')
            explicit = next((x for x in before if not seeded(x) and x['id'] != p.STUDY), None)
            titles = [(p.STUDY, p.EXPECTED_TITLE)] + ([(explicit['id'], explicit['title'])] if explicit else [])
            entry['titles'] = []
            for identity, title in titles:
                code, raw = p.request('/papers/' + identity + '/title')
                require(code == 200 and len(raw) <= 200_000, 'Source-title endpoint is unavailable.')
                data = json.loads(raw)
                require(data == dict(version='research-paper-catalog-v1', access='public-read-only', id=identity, title=title), 'Retained source-title result differs.')
                entry['titles'].append(dict(id=identity, title=title, sha256=sha(raw)))
            entry['negative_checks'] = []
            paths = [('/papers?before=invalid', 'GET', {400}), ('/papers/00000000-0000-4000-8000-000000000001/title', 'GET', {404}), ('/papers', 'POST', {401, 404, 405})]
            ideas = r.admin.query("select id::text from research_studies where study_kind='idea' order by id limit 1")
            if ideas:
                paths.append(('/papers/' + ideas[0]['id'] + '/title', 'GET', {404}))
            for path, method, accepted in paths:
                status, _ = p.request(path, method)
                require(status in accepted, 'Invalid/missing/private catalog route was not rejected.')
                entry['negative_checks'].append(dict(path=path, method=method, status=status))
            return
        except Exception as error:
            entry.update(status='failed', reason=str(error))
            raise
    raise RuntimeError('Catalog did not stabilize within three retained attempts.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['baseline', 'diff', 'deploy', 'check'])
    args = parser.parse_args()
    directory = ROOT / '.test-artifacts/assessment-catalog-release' / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True)
    report = dict(protocol=PROTOCOL, mode=args.mode, backend_revision=BACKEND, status='running', started_at=stamp(), measured_charges_usd=None, new_experiment_launches=0, research_model_calls=0)
    try:
        manifest_raw = (ROOT / 'research-workflow-runtime.json').read_bytes()
        manifest = r.prior.queue.source()
        require(manifest['version'] == 38 and manifest['source_revision'] == BACKEND and len(manifest['files']) == 34, 'Unexpected runtime revision/bound.')
        report['runtime_manifest_sha256'] = sha(manifest_raw)
        report['targets'] = r.target()
        if args.mode == 'baseline':
            report['baseline'] = identities()
        elif args.mode in ('diff', 'deploy'):
            report['cdk'] = r.cdk(args.mode, directory, activate=True)
        else:
            baselines = []
            for file in directory.parent.glob('*/receipt.json'):
                candidate = json.loads(file.read_bytes())
                if candidate.get('mode') == 'baseline' and candidate.get('backend_revision') == BACKEND and candidate.get('status') == 'passed':
                    baselines.append(file)
            require(baselines, 'A retained pre-release baseline is required.')
            baseline_file = max(baselines)
            baseline_raw = baseline_file.read_bytes()
            report['baseline_receipt'] = dict(path=str(baseline_file.relative_to(ROOT)), sha256=sha(baseline_raw))
            report['catalog_attempts'] = []
            catalog(directory, report['catalog_attempts'])
            report['title_evidence'] = p.title_evidence(directory)
            report['public_queue'] = p.public_check(directory)
            report['after'] = identities()
            require(report['after'] == json.loads(baseline_raw)['baseline'], 'Retained paper metadata/initial prompts or active prompt settings changed.')
            report['immutable_identities_preserved'] = True
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', reason=str(error))
        raise
    finally:
        report['ended_at'] = stamp()
        (directory / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(dict(directory=str(directory), **report), indent=2))


if __name__ == '__main__':
    main()
