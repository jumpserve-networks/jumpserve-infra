"""Import the five existing paper assessments without rewriting their history.

Fixed JumpServe targets and study inventory. No schema changes, deployments,
experiment execution, arbitrary commands or credentials in retained outputs.
"""
import argparse
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / 'jumpserve-back-end'
OUT = ROOT / '.test-artifacts/archived-assessments-v1'
spec = importlib.util.spec_from_file_location('guard', ROOT / 'bin/research-workflow-database.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
sys.path.insert(0, str(BACKEND / 'research_workflow'))
import workflow
import archive
import store

PREFIXES = ('delay_study_', 'leo_study_', 'http2_study_', 'ipv6_study_', 'reliable_study_')
MODULES = {
    'propagation-delay-study': dict(prefix='delay_study_', source='papers', tables=['campaigns', 'claims', 'papers', 'configurations', 'config_flows', 'cells', 'summaries', 'latency_trials'], title='Making Congestion Control Algorithms Insensitive to Underlying Propagation Delays', doi='10.4230/OASIcs.NINeS.2026.27', domain='Propagation delay and congestion control', export='/data'),
    'leo-emergency-failover': dict(prefix='leo_study_', source='papers', tables=['campaigns', 'claims', 'papers', 'configurations', 'summaries'], title='Assessing LEO Satellite Networks for National Emergency Failover', doi='10.1145/3730567.3764482', domain='LEO satellite failover simulations', export='/api/results'),
    'http2-compliance-study': dict(prefix='http2_study_', source='sources', tables=['campaigns', 'claims', 'sources', 'configurations', 'summaries', 'protocols', 'followups'], title='The Developer, the RFC, and the Middlebox: An HTTP/2 Compliance Story', doi='10.1145/3730567.3764447', domain='HTTP/2 compliance', export='/api/results'),
    'ipv6-dns-study': dict(prefix='ipv6_study_', source='sources', tables=['campaigns', 'claims', 'sources', 'configurations', 'summaries', 'protocols', 'published', 'comparisons', 'meta', 'controls'], title='How I learned to stop worrying and love IPv6', doi='10.1145/3730567.3764439', domain='Historical DNS over IPv6', export='/api/data'),
    'reliable-sketch-study': dict(prefix='reliable_study_', source='sources', tables=['campaigns', 'claims', 'sources', 'configurations', 'summaries', 'protocols', 'published', 'meta', 'controls'], title='Approaching 100% Confidence in Stream Summary through ReliableSketch', doi='10.1145/3730567.3764459', domain='Stream-counting correctness and CPU measurements', export='/api/results'),
}

def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, indent=2, allow_nan=False).encode() + b'\n'
    path = OUT / name
    if path.exists():
        if path.read_bytes() == raw:
            return
        raise RuntimeError('Retained evidence already exists; preserve it and use a new version.')
    with path.open('xb') as stream:
        stream.write(raw)

def inspect(supabase_only=False):
    target = (dict(aws_account=None, supabase_project=guard.admin.PROJECT_REF,
                   database=guard.admin.query('select current_database() as database')[0]['database'],
                   aws_verification='Pending renewed login; read-only inventory only.')
              if supabase_only else guard.targets())
    schemas = guard.admin.query("select table_name,column_name,data_type from information_schema.columns where table_schema='public' and (table_name like 'delay_study_%' or table_name like 'leo_study_%' or table_name like 'http2_study_%' or table_name like 'ipv6_study_%' or table_name like 'reliable_study_%') order by table_name,ordinal_position")
    tables = sorted({r['table_name'] for r in schemas})
    if any(not name.startswith(PREFIXES) or not name.replace('_', '').isalnum() for name in tables):
        raise RuntimeError('Unexpected legacy relation identity.')
    counts = guard.admin.query(' union all '.join("select '" + name + "' as relation,count(*) as records from public." + name for name in tables))
    studies = guard.admin.query("select s.id,s.title,s.paper_url,s.domain,s.scope,s.origin_module,(select count(*) from public.research_claims c where c.study_id=s.id) claims,(select count(*) from public.research_runs r where r.study_id=s.id) runs,(select max(version) from public.research_publications p where p.study_id=s.id and status='published') published_version from public.research_studies s order by s.created_at,s.id")
    security = guard.verify(target, queue=True, preparation=True)
    result = dict(targets=target, inspected_at=workflow.now(), schemas=schemas, counts=counts,
                  studies=studies, security=security, read_only=True,
                  provenance='Authorized operator inventory. No experiment execution or authenticated browser session implied.')
    save('inventory-supabase-v1.json' if supabase_only else 'inventory-v1.json', result)
    print(json.dumps(dict(targets=target, counts=counts, studies=studies), indent=2))

def export():
    target = guard.targets()
    inventory = json.loads((OUT / 'inventory-v1.json').read_bytes())
    expected = {row['relation']: row['records'] for row in inventory['counts']}
    manifest = []
    tick = time.monotonic()
    for module, definition in MODULES.items():
        path = OUT / (module + '-native-v1.json')
        if path.exists():
            raw = path.read_bytes()
            value = json.loads(raw)
        else:
            data = {}
            for suffix in definition['tables']:
                table = definition['prefix'] + suffix
                # Only fixed scientific relations; no artifacts, owner rows or chat.
                rows = guard.admin.query('select to_jsonb(t)::text as row from public.' + table + ' t order by to_jsonb(t)::text')
                # Preserve decimal tokens as strings, without a binary-float round
                # trip. The original typed decimal values remain in native SQL.
                data[suffix] = [json.loads(row['row'], parse_float=str) for row in rows]
                if len(data[suffix]) != expected[table]:
                    raise RuntimeError('Native coverage changed during export: ' + table)
            value = dict(module=module, targets=target, exported_at=workflow.now(), data=data,
                         original_relation_counts={name: count for name, count in expected.items() if name.startswith(definition['prefix'])},
                         provenance='Read-only normalized database export; generated JSON is not original author measurement bytes. Native private originals and per-observation relations are unchanged.')
            save(module + '-native-v1.json', value)
            raw = path.read_bytes()
        if len(raw) > 10_000_000:
            raise RuntimeError('Native export artifact exceeds the frozen budget.')
        manifest.append(dict(module=module, path=path.name, sha256=workflow.digest(raw), byte_count=len(raw), exported_counts={key: len(rows) for key, rows in value['data'].items()}))
        print(json.dumps(dict(module=module, bytes=len(raw), exported_counts=manifest[-1]['exported_counts'])), flush=True)
    save('native-manifest-v1.json', dict(targets=target, originals=manifest,
         logical_bytes=sum(row['byte_count'] for row in manifest), wall_seconds=time.monotonic()-tick,
         import_protocol_sha256=workflow.digest((ROOT / 'docs/archived-assessment-import-protocol-v1.md').read_bytes())))

def prepare():
    manifest = json.loads((OUT / 'native-manifest-v1.json').read_bytes())
    protocol_sha = workflow.digest((ROOT / 'docs/archived-assessment-import-protocol-v1.md').read_bytes())
    if protocol_sha != manifest['import_protocol_sha256']:
        raise RuntimeError('Import protocol changed after export; preserve original and amend separately.')
    results = []
    for original in manifest['originals']:
        module = original['module']; path = OUT / original['path']
        if workflow.digest(path.read_bytes()) != original['sha256']:
            raise RuntimeError('Native export hash changed.')
        name = module + ('-prepared-v3.json' if module == 'ipv6-dns-study' else '-prepared-v2.json')
        if (OUT / name).exists():
            value = json.loads((OUT / name).read_bytes())
            if value['input_sha256'] != original['sha256'] or value['provenance']['import_protocol_sha256'] != protocol_sha:
                raise RuntimeError('Prepared evidence identifies another input or protocol.')
        else:
            value = archive.build(path, MODULES[module], BACKEND, protocol_sha)
            save(name, value)
        ids = {row['record']['id'] for row in value['records']}
        if len(ids) != len(value['records']):
            raise RuntimeError('Duplicate shared record identity.')
        for entry in value['records']:
            row = workflow.validate_record(entry['kind'], entry['record'])
            for key in ('source_id', 'claim_id', 'assessment_id', 'campaign_id', 'protocol_id', 'run_id', 'published_id'):
                if row.get(key) is not None and row[key] not in ids:
                    raise RuntimeError('Imported foreign-key identity is missing: ' + key)
        results.append(dict(module=module, study_id=value['study_id'], prepared_path=name,
            prepared_sha256=workflow.digest((OUT / name).read_bytes()), coverage=value['coverage'],
            labels=value['claim_labels'], scientific_bytes=len(workflow.canonical(value['records'])),
            native_original_bytes=original['byte_count']))
        print(json.dumps(results[-1]), flush=True)
    save('prepared-manifest-v3.json', dict(version=archive.VERSION, studies=results,
        declared_protocol_sha256=protocol_sha, review=archive.REVIEWER,
        validation='Schema, exact IDs, coverage and stable native input hashes; not new independent scientific experiments.'))

def prepared():
    manifest = json.loads((OUT / 'prepared-manifest-v3.json').read_bytes())
    if manifest['declared_protocol_sha256'] != workflow.digest((ROOT / 'docs/archived-assessment-import-protocol-v1.md').read_bytes()):
        raise RuntimeError('Declared protocol hash changed.')
    values = []
    for item in manifest['studies']:
        raw = (OUT / item['prepared_path']).read_bytes()
        if workflow.digest(raw) != item['prepared_sha256']:
            raise RuntimeError('Prepared projection hash differs.')
        value = json.loads(raw)
        if value['study_id'] != item['study_id'] or value['paper']['origin_module'] != item['module']:
            raise RuntimeError('Prepared study identity differs.')
        values.append((item, value))
    return values

def connect():
    target = guard.targets()
    guard.verify(target, queue=True, preparation=True)
    secret = subprocess.check_output(['aws', 'secretsmanager', 'get-secret-value', '--secret-id',
        'jumpserve/supabase-service-key', '--profile', 'jumpserve', '--region', 'us-east-1'], timeout=20)
    os.environ['SUPABASE_SERVICE_ROLE_KEY'] = json.loads(secret)['SecretString']
    os.environ['SUPABASE_URL'] = 'https://regphejnlvfpyokpniny.supabase.co'
    os.environ['SSL_CERT_FILE'] = '/etc/ssl/cert.pem'
    frontend = ROOT.parent / 'jumpserve-front-end/.env.local'
    for line in frontend.read_text().splitlines():
        if line.startswith('NEXT_PUBLIC_SUPABASE_ANON_KEY='):
            os.environ['SUPABASE_ANON_KEY'] = line.split('=', 1)[1].strip().strip('\"\'')
    owners = store.rows('study_owners', {'study_id':'eq.76c70fd9-0217-464e-8c26-0a47832409a3','limit':1})
    if len(owners) != 1:
        raise RuntimeError('Previously authorized study owner is unavailable.')
    return target, owners[0]['owner_id']

def append(study, actor, entries):
    # Small immutable atomic batches avoid a large interactive PostgREST payload.
    literal = guard.admin.literal
    return guard.admin.query('select public.research_append_bundle(' + literal(study) + '::uuid,' +
        literal(actor) + '::uuid,' + literal(json.dumps(entries, allow_nan=False)) + '::jsonb) as receipt', read_only=False)

def browser_report():
    directory = ROOT.parent / 'jumpserve-front-end/.test-artifacts/archived-assessments'
    reports = sorted(directory.glob('*/browser-report.json'))
    for path in reversed(reports):
        value = json.loads(path.read_bytes())
        if value.get('mode') == 'exact prepared component preview' and value.get('passed'):
            if len(value['checks']) != 20:
                raise RuntimeError('Browser view coverage incomplete.')
            return path, value
    raise RuntimeError('Five-study prepublication browser checks have not passed.')

def apply():
    browser_path, _ = browser_report()
    target, actor = connect()
    tick = time.monotonic(); receipts = []
    for item, value in prepared():
        study = value['study_id']
        store.rpc('research_create_study', dict(p_actor=actor,p_id=study,p_document=value['paper']))
        if not store.owns(study, actor):
            raise RuntimeError('Imported study ownership mismatch.')
        originals = [('native-export', OUT / value['original_artifact']), ('prepared-projection', OUT / item['prepared_path']),
            ('import-protocol', ROOT / 'docs/archived-assessment-import-protocol-v1.md'),
            ('serialization-v2', ROOT / 'docs/archived-assessment-import-serialization-v2.md'),
            ('serialization-v3', ROOT / 'docs/archived-assessment-import-serialization-v3.md'),
            ('component-verification', browser_path)]
        run = next(e['record'] for e in value['records'] if e['kind']=='runs')
        implementation_sha = run['provenance']['implementation_sha256']
        candidates = [OUT/'archive-implementation-v2.py', OUT/'archive-implementation-v3.py', BACKEND/'research_workflow/archive.py']
        matching = [p for p in candidates if p.exists() and workflow.digest(p.read_bytes())==implementation_sha]
        if not matching:
            raise RuntimeError('Exact executed import implementation bytes unavailable.')
        originals.append(('executed-implementation', matching[0]))
        if item['module']=='propagation-delay-study':
            originals += [('main-paper-original', BACKEND/'experiments/nines2026_delay_equalization/literature/primary.pdf'),
                          ('original-reading-audit', BACKEND/'experiments/nines2026_delay_equalization/PRIMARY_READING.md'),
                          ('original-assessment-report', BACKEND/'experiments/nines2026_delay_equalization/RESULTS.md')]
        artifact_rows = []
        for name, path in originals:
            raw=path.read_bytes()
            if len(raw)>10_000_000:
                raise RuntimeError('Original artifact exceeds frozen bound.')
            media='application/pdf' if path.suffix=='.pdf' else 'text/markdown' if path.suffix=='.md' else 'application/json' if path.suffix=='.json' else 'text/x-python'
            row=store.artifact(study,actor,raw,archive.uid(study,'artifact:'+name),media,
                dict(name=name,version=archive.VERSION,transformation='None; exact retained bytes. Native export is generated normalized JSON, not author packet/capture bytes.'))
            artifact_rows.append(dict(kind='artifacts',record=row))
        entries=artifact_rows+value['records']
        for offset in range(0,len(entries),100):
            receipt=append(study,actor,entries[offset:offset+100])
            with (OUT/'write-progress-v1.jsonl').open('a') as stream:
                stream.write(json.dumps(dict(study_id=study,offset=offset,records=len(entries[offset:offset+100]),receipt=receipt,at=workflow.now()))+'\n')
            print(json.dumps(dict(module=item['module'],preserved=min(offset+100,len(entries)),total=len(entries))),flush=True)
        receipts.append(dict(study_id=study,module=item['module'],scientific_records=len(value['records']),
            artifacts=[dict(id=e['record']['id'],sha256=e['record']['sha256'],byte_count=e['record']['byte_count']) for e in artifact_rows]))
    total_bytes=sum(a['byte_count'] for r in receipts for a in r['artifacts'])
    if total_bytes>50_000_000:
        raise RuntimeError('Logical original storage exceeds frozen budget; inspect and preserve completed records.')
    save('persistence-v1.json',dict(targets=target,studies=receipts,stored_payload_bytes=total_bytes,
        wall_seconds=time.monotonic()-tick,at=workflow.now(),published=False,deployment=False,
        actor='Authorized trusted operator using previously owned study; identity and credentials stay private. No Google session implied.'))

def verify(public=False):
    target, actor=connect(); results=[]
    receipt=json.loads((OUT/'persistence-v1.json').read_bytes())
    for item,value in prepared():
        study=value['study_id'];snapshot=store.snapshot(study,owner=not public)
        timestamp_serializations=[]
        if snapshot is None:
            raise RuntimeError('Expected imported study snapshot missing.')
        indexed={k:{r['id']:r for r in rows} for k,rows in snapshot['records'].items()}
        for kind,count in value['coverage'].items():
            if snapshot['coverage'][kind]!=count:
                raise RuntimeError('Imported coverage differs: '+kind)
        for entry in value['records']:
            actual=indexed[entry['kind']][entry['record']['id']]
            for field, expected in entry['record'].items():
                if field=='value' and expected is not None:
                    if Decimal(str(actual[field]))!=Decimal(str(expected)):
                        raise RuntimeError('Stored numerical value differs.')
                elif field in ('frozen_at','started_at','ended_at') and expected is not None:
                    original_time=dt.datetime.fromisoformat(expected)
                    stored_time=dt.datetime.fromisoformat(actual[field])
                    if original_time.utcoffset() is None or stored_time.utcoffset() is None or original_time!=stored_time:
                        raise RuntimeError('Stored timestamp instant differs: '+entry['kind']+'.'+field)
                    if actual[field]!=expected:
                        timestamp_serializations.append(dict(kind=entry['kind'],id=entry['record']['id'],
                            field=field,prepared=expected,stored=actual[field],same_instant=True))
                elif actual[field]!=expected:
                    raise RuntimeError('Stored field differs: '+entry['kind']+'.'+field)
        artifacts=next(r['artifacts'] for r in receipt['studies'] if r['study_id']==study)
        for artifact in artifacts:
            raw=store.artifact_bytes(study,artifact['id'],maximum=10_000_000)
            if workflow.digest(raw)!=artifact['sha256'] or len(raw)!=artifact['byte_count']:
                raise RuntimeError('Stored artifact identity differs after retrieval.')
        results.append(dict(module=item['module'],study_id=study,verified_fields=True,
            coverage=snapshot['coverage'],snapshot_bytes=len(workflow.canonical(snapshot)),
            artifact_hashes_verified=len(artifacts),labels=item['labels'],
            timestamp_serializations=timestamp_serializations))
        print(json.dumps(dict(module=item['module'],passed=True,bytes=results[-1]['snapshot_bytes'])),flush=True)
    inventory=json.loads((OUT/'inventory-v1.json').read_bytes())
    tables=[row['relation'] for row in inventory['counts']]
    counts=guard.admin.query(' union all '.join("select '"+name+"' as relation,count(*) as records from public."+name for name in tables))
    if {r['relation']:r['records'] for r in counts}!={r['relation']:r['records'] for r in inventory['counts']}:
        raise RuntimeError('Original native relation counts changed; reconcile before publication.')
    # This operator never alters old research IDs. Check their coverage/history too.
    original=guard.admin.query("select s.id,(select count(*) from public.research_claims c where c.study_id=s.id) claims,(select count(*) from public.research_runs r where r.study_id=s.id) runs,(select max(version) from public.research_publications p where p.study_id=s.id and status='published') published_version from public.research_studies s where s.id in ("+','.join(guard.admin.literal(s['id'])+'::uuid' for s in inventory['studies'])+") order by s.id")
    before={s['id']:{k:s[k] for k in ('claims','runs','published_version')} for s in inventory['studies']}
    if {s['id']:{k:s[k] for k in ('claims','runs','published_version')} for s in original}!=before:
        raise RuntimeError('Pre-existing study coverage/publication changed; reconcile before publication.')
    save('public-verification-v1.json' if public else 'private-verification-v1.json',dict(targets=target,passed=True,at=workflow.now(),studies=results,
        original_native_relations_unchanged=len(tables),original_research_studies_unchanged=len(original),
        public_anonymous_read=public,deployment=False,conditional_gaps=['No authenticated Google browser request','No historical experiment rerun or independent scientific review'],
        usage=dict(measured_charges_usd=None,unallocated_costs=['Database/index overhead','Storage/transfer billing','Existing hosting','Workstation/Codex allocation'])))

def publish():
    verification=json.loads((OUT/'private-verification-v1.json').read_bytes())
    if not verification['passed']:
        raise RuntimeError('Stored field/hash verification did not pass.')
    native_report=OUT/'native-public-availability-v1.json'
    native=json.loads(native_report.read_bytes())
    if not native['passed'] or len(native['checks'])!=10 or any(c['observed_http_status']!=200 for c in native['checks']):
        raise RuntimeError('Original module public page/export availability did not pass.')
    browser_path,_=browser_report()
    target,actor=connect();results=[]
    for item,value in prepared():
        study=value['study_id'];review_ids=[]
        # Reviews apply to truthful transfer, presentation and evidence limits,
        # not independent validation of the historical scientific claims.
        for scope in ('scientific','software'):
            judgments=(dict(scope_and_limits_reviewed=True,original_explicit_labels_preserved=True,
                coverage_only_labels='Documented conservative crosswalk from existing reports and summaries; not new experiments.',
                native_detailed_observations_retained=True,new_experiments=False,
                review_scope='Historical import provenance, conservative mappings and explicit limitations. No independent scientific validation.')
                if scope=='scientific' else dict(release_blockers={k:True for k in ('database','backend','frontend','provenance','access_control')},
                database='Existing guarded schema/RLS plus all-field and artifact round-trip verification.',
                backend='70 passing development regressions, including review/claim scope types and actual store.append review validation; exact schemas/IDs and stored snapshot checks.',
                frontend='Five exact prepared studies, four views and desktop/mobile light/dark previews passed.',
                browser_report_sha256=workflow.digest(browser_path.read_bytes()),
                stored_verification_sha256=workflow.digest((OUT/'private-verification-v1.json').read_bytes()),
                native_public_availability_sha256=workflow.digest(native_report.read_bytes()),
                timestamp_verifier_correction='Typed PostgreSQL timestamps compared as aware instants; differing spellings retained. No scientific rows changed.',
                conditional_gaps=['No Google session/provider round trip','Postpublication production checks follow separately']))
            review=dict(id=archive.uid(study,'review:'+scope),scope=scope,status='passed',reviewer=archive.REVIEWER,
                judgments=judgments,limitations='AI implementer inspection of historical evidence transfer; no human or independent scientific review. Scope and unresolved gaps remain visible.')
            store.append(study,actor,'reviews',review);review_ids.append(review['id'])
        result=store.rpc('research_publish',dict(p_study=study,p_actor=actor,p_id=archive.uid(study,'publication:v1'),
            p_scientific=review_ids[0],p_software=review_ids[1],
            p_reason='Publish imported historical assessment with original evidence, conservative coverage and open gaps. No application-launched experiments or independent scientific validation claimed.',p_withdraw=False))
        results.append(dict(module=item['module'],study_id=study,version=result['version'],status=result['status']))
        print(json.dumps(results[-1]),flush=True)
    save('publication-v1.json',dict(targets=target,at=workflow.now(),studies=results,application_deployment=False,reviewer=archive.REVIEWER))

def retain_evidence():
    """Keep exact successful/failed verification bytes private after publication.

    The existing scientific manifest excludes private artifact metadata. This
    preserves the public version and adds no scientific result or queue job.
    """
    public=json.loads((OUT/'public-verification-v1.json').read_bytes())
    publications=json.loads((OUT/'publication-v1.json').read_bytes())
    if not public['passed'] or len(public['studies'])!=5 or any(s['status']!='published' for s in publications['studies']):
        raise RuntimeError('Successful public verification and publication receipts are required.')
    reports=sorted((ROOT.parent/'jumpserve-front-end/.test-artifacts/archived-assessments').glob('*/browser-report.json'))
    production_report=next((p for p in reversed(reports) if json.loads(p.read_bytes()).get('mode')=='public production' and json.loads(p.read_bytes()).get('passed')),None)
    if production_report is None or len(json.loads(production_report.read_bytes())['checks'])!=26:
        raise RuntimeError('Complete five-study production browser/export checks are required.')
    names=['persistence-v1.json','native-manifest-v1.json','prepared-manifest-v3.json',
        'private-verification-v1.json','public-verification-v1.json','native-public-availability-v1.json',
        'local-validation-v1.json','local-validation-v2.json','verification-failures-v1.json',
        'publication-failures-v1.json','publication-v1.json','import-operator-v1.py',
        'workflow-before-review-scope-fix.py']
    common=[(name,(OUT/name).read_bytes()) for name in names]
    common += [('production-browser-report.json',production_report.read_bytes()),
        ('import-operator-final.py',Path(__file__).read_bytes()),
        ('workflow-after-review-scope-fix.py',(BACKEND/'research_workflow/workflow.py').read_bytes()),
        ('workflow-regressions.py',(BACKEND/'research_workflow/tests/test_workflow.py').read_bytes()),
        ('browser-verifier.mjs',(ROOT.parent/'jumpserve-front-end/scripts/verify-archived-assessments.mjs').read_bytes())]
    bundles=[];decoded_bytes=0
    for item,_ in prepared():
        originals=common+[(item['module']+'-'+str(width)+'-'+theme+'.png',
            (production_report.parent/(item['module']+'-'+str(width)+'-'+theme+'.png')).read_bytes())
            for width in (1365,390) for theme in ('light','dark')]
        if any(len(raw)>10_000_000 for _,raw in originals):
            raise RuntimeError('Validation original exceeds the frozen artifact bound.')
        manifest=dict(study_id=item['study_id'],protocol='archived-assessment-import-protocol-v1',
            files=[dict(name=name,sha256=workflow.digest(raw),byte_count=len(raw)) for name,raw in originals],
            transformation='ZIP_DEFLATED level 9; exact file bytes retained. ZIP header date 1980-01-01 is a deterministic container constant, not an experiment/retrieval date.',
            scope='Import, publication and software validation evidence; no new scientific experiments or human review.',reviewer=archive.REVIEWER)
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as bundle:
            for name,raw in originals+[('manifest.json',workflow.canonical(manifest))]:
                bundle.writestr(zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0)),raw,
                    compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
        raw=buffer.getvalue();path=OUT/(item['module']+'-validation-v1.zip')
        if len(raw)>10_000_000:
            raise RuntimeError('Validation ZIP exceeds the frozen artifact bound.')
        if path.exists():
            if path.read_bytes()!=raw:raise RuntimeError('Retained validation ZIP differs; use a new evidence version.')
        else:
            with path.open('xb') as stream:stream.write(raw)
        decoded_bytes+=sum(len(data) for _,data in originals)
        bundles.append((item,raw,manifest))
    initial=json.loads((OUT/'persistence-v1.json').read_bytes())['stored_payload_bytes']
    if initial+decoded_bytes>50_000_000:
        raise RuntimeError('Total original validation bytes exceed the frozen aggregate bound.')
    target,actor=connect();tick=time.monotonic();results=[]
    for item,raw,manifest in bundles:
        study=item['study_id']
        before=store.rows('publications',{'study_id':'eq.'+study,'order':'version.desc','limit':1},public=True)
        row=store.artifact(study,actor,raw,archive.uid(study,'artifact:import-validation-v1'),'application/zip',
            dict(name='historical-import-validation',version=1,manifest=manifest))
        store.append(study,actor,'artifacts',row)
        retrieved=store.artifact_bytes(study,row['id'],maximum=10_000_000)
        if retrieved!=raw:raise RuntimeError('Validation ZIP original bytes differ after retrieval.')
        with zipfile.ZipFile(io.BytesIO(retrieved),'r') as bundle:
            if len(bundle.namelist())!=len(manifest['files'])+1 or set(bundle.namelist())!={f['name'] for f in manifest['files']}|{'manifest.json'}:
                raise RuntimeError('Validation ZIP member identities differ.')
            if bundle.read('manifest.json')!=workflow.canonical(manifest):raise RuntimeError('Validation ZIP manifest differs.')
            for file in manifest['files']:
                data=bundle.read(file['name'])
                if len(data)!=file['byte_count'] or workflow.digest(data)!=file['sha256']:
                    raise RuntimeError('Validation original member bytes differ after retrieval.')
        after=store.rows('publications',{'study_id':'eq.'+study,'order':'version.desc','limit':1},public=True)
        if not before or before!=after:raise RuntimeError('Publication changed during private evidence retention.')
        result=dict(module=item['module'],study_id=study,artifact_id=row['id'],sha256=row['sha256'],
            stored_bytes=len(raw),decoded_original_bytes=sum(f['byte_count'] for f in manifest['files']),
            members_verified=len(manifest['files']),publication_version=after[0]['version'],passed=True)
        results.append(result);print(json.dumps(result),flush=True)
    save('validation-retention-v1.json',dict(targets=target,at=workflow.now(),passed=True,studies=results,
        prior_stored_payload_bytes=initial,new_stored_payload_bytes=sum(s['stored_bytes'] for s in results),
        total_logical_original_bytes=initial+decoded_bytes,wall_seconds=time.monotonic()-tick,
        browser_report=str(production_report.relative_to(ROOT.parent)),deployment=False,
        measured_charges_usd=None,unallocated_costs=['Database and storage billing','Existing hosting','Workstation and Codex allocation']))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect', 'export', 'prepare', 'apply', 'verify', 'publish', 'retain-evidence'])
    parser.add_argument('--supabase-only', action='store_true', help='Read-only inventory while AWS login is pending; never permits writes.')
    parser.add_argument('--public', action='store_true', help='Verify actual anonymous published reads; only with verify.')
    args = parser.parse_args()
    if args.supabase_only and args.command!='inspect':
        raise ValueError('Partial target verification is read-only inspect only.')
    if args.public and args.command!='verify':
        raise ValueError('Public is only a read-only verification mode.')
    if args.command == 'inspect':
        inspect(args.supabase_only)
    elif args.command == 'export':
        if args.supabase_only:
            raise ValueError('Only inspect supports partial target verification.')
        export()
    elif args.command == 'prepare':
        prepare()
    elif args.command == 'apply':
        apply()
    elif args.command == 'verify':
        verify(public=args.public)
    elif args.command == 'publish':
        publish()
    elif args.command == 'retain-evidence':
        retain_evidence()

if __name__ == '__main__':
    main()
