"""One fixed private cloud TCP instrumentation control, never a paper finding."""
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'bin'), str(ROOT.parent / 'jumpserve-back-end/research_workflow')]
spec = importlib.util.spec_from_file_location('bounded_release', ROOT / 'bin/autonomy-followup-release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)
import autonomy, network_spec, scheduler, store, workflow
BASE = ROOT / '.test-artifacts/bounded-autonomy-production/v1'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
uid = lambda: str(uuid.uuid4())


def main():
    resume = sys.argv[1:] == ['--resume-prerequisites']
    if len(sys.argv) != 1 and not resume: raise RuntimeError('Only the fixed initial control or its pre-admission prerequisite correction is allowed')
    directory = BASE.parent / 'v2' if resume else BASE
    directory.mkdir(parents=True, exist_ok=True); path = directory / 'report.json'
    if path.exists(): raise RuntimeError('Control already attempted; inspect retained identities, never relaunch')
    report = dict(status='running', protocol='autonomy-bounded-followups-release-protocol-v1',
        started_at=dt.datetime.now(dt.timezone.utc).isoformat(), reviewer=dict(identity='Primary Codex AI implementer', type='AI', independent=False),
        origin='Actual new TCP measurements inside the deployed Lambda; host-local instrumentation control, not Internet/CDN or paper-claim evidence.',
        actor='Service release operator; not a Google-authenticated browser action', new_model_calls=0, new_ec2_instances=0, measured_charges_usd=None)
    def checkpoint(): path.write_text(json.dumps(report, indent=2) + '\n')
    checkpoint()
    try:
        release.reviewed(); report['targets'] = release.prior.guard.target()
        functions = release.prior.functions(directory, True)
        worker = next(f for f in functions if f['handler'] == 'worker.handler')
        config = release.prior.aws('lambda', 'get-function-configuration', '--function-name', worker['arn'])
        variables = config['Environment']['Variables']
        if variables['SUPABASE_URL'] != 'https://regphejnlvfpyokpniny.supabase.co': raise RuntimeError('Production target differs')
        os.environ.update(SUPABASE_URL=variables['SUPABASE_URL'], SUPABASE_SERVICE_ROLE_KEY=release.prior.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'],
            SUPABASE_ANON_KEY=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'], SSL_CERT_FILE='/etc/ssl/cert.pem',
            NETWORK_BOUNDED_FUNCTION=variables['NETWORK_BOUNDED_FUNCTION'], NETWORK_BOUNDED_POLICY_SHA256=variables['NETWORK_BOUNDED_POLICY_SHA256'])
        if resume:
            original_path = BASE / 'report.json'; original = json.loads(original_path.read_bytes())
            if original['status'] != 'failed' or any(key in original for key in ('queue_admission','worker_invocation','run_id')):
                raise RuntimeError('Only the retained pre-admission failure may resume; never replay unknown dispatch')
            study, protocol, campaign, job = [original[key] for key in ('study_id','protocol_id','campaign_id','job_id')]
            if store.rows('queue_jobs',dict(study_id='eq.'+study)) or store.rows('runs',dict(study_id='eq.'+study)):
                raise RuntimeError('Existing queue or execution requires inspection, not a second launch')
            owners = store.rows('study_owners',dict(study_id='eq.'+study))
            if len(owners) != 1: raise RuntimeError('Expected the single retained service-operator owner')
            actor = owners[0]['owner_id']
            report['amendment'] = dict(original_report=str(original_path.relative_to(ROOT)),original_sha256=sha(original_path.read_bytes()),
                reason='Add the omitted applicable software-control claim/check after confirmed pre-admission rejection; reuse all retained configuration, protocol, campaign and job identities.',
                absent_queue_and_run_verified=True,original_failure_preserved=True)
        else:
            study, actor, protocol, campaign, job = [uid() for _ in range(5)]
        report.update(study_id=study, protocol_id=protocol, campaign_id=campaign, job_id=job); checkpoint()
        # A private auxiliary instrumentation campaign; its software-control
        # claim is not an academic paper claim, assessment or publication.
        if not resume: store.rpc('research_create_study',dict(p_actor=actor,p_id=study,p_document=workflow.paper_details(dict(title='Production bounded TCP instrumentation release verification',
            domain='Networking instrumentation software control', study_kind='paper',
            paper_url='https://pure.mpg.de/pubman/item/item_3670144_1/component/file_3670145/main.pdf',
            scope='Auxiliary host-local instrumentation control only. Does not assess a claim of the cited paper; service-operator release verification.'))))
        p = workflow.numerical_protocol('a'*64,'round_trip_time_ms','ms',0,[dict(identity='release-loopback',details=dict(test_config=dict(payload_bytes=32,exchanges=2,application_delay_ms=2)))])
        p.update(questions=['Does the deployed bounded TCP queue preserve exact measurements and original bytes?'],hypotheses='Software instrumentation control; received payload bytes equal 32 in each exchange.',
            prior_exposure='Predeclared release control; exposed software checks, no population inference.',data_origin='new-empirical',planned_units=1,
            statistics='Descriptive individual exchange observations only; no confidence interval.',dependence='One Lambda host/process/connection; repeated exchanges are correlated.',replication_unit='One complete immutable function invocation.',
            resource_limits=dict(max_input_bytes=10000,max_observations=4,wall_seconds=60),
            metrics=[dict(name='round_trip_time_ms',units='ms',planned_observations=2,lower_bound=0),dict(name='received_bytes',units='bytes',planned_observations=2,lower_bound=0)],
            execution=dict(version=network_spec.VERSION,runner='bounded-tcp-v1',replications=1,limits=dict(wall_seconds=60,max_instances=1,max_output_bytes=32000,max_network_bytes=1024)),
            input_versions=[],algorithms=['bounded-tcp-v1: immutable TCP loopback payload exchanges.'],controls=['Exact payload integrity, fixed endpoint, numeric-only configuration.'],
            sample_size_rationale='Two exchanges test instrumentation; no statistical power or independent-replication claim.',coverage_limits='Lambda host-local control only; no academic paper, Internet or CDN validation.',
            stopping_rule='Two exchanges or fixed watchdog/deadline. No automatic retry after uncertain dispatch.')
        p = network_spec.bind_inputs(p); execution = network_spec.specs(p)[0]; raw = workflow.canonical(execution)
        if resume:
            retained = store.rows('protocols',dict(study_id='eq.'+study,id='eq.'+protocol))
            campaigns = store.rows('campaigns',dict(study_id='eq.'+study,id='eq.'+campaign))
            studies = store.rows('studies',dict(id='eq.'+study))
            if len(retained)!=1 or len(campaigns)!=1 or len(studies)!=1 or studies[0]['title']!='Production bounded TCP instrumentation release verification':
                raise RuntimeError('Retained private control identity differs')
            if retained[0]['document']!=p or retained[0]['sha256']!=sha(workflow.canonical(p)) or campaigns[0]['protocol_id']!=protocol or sha(raw)!=original['configuration_sha256']:
                raise RuntimeError('Frozen original protocol/configuration differs; no amendment of scientific inputs allowed')
        report['configuration'] = execution; report['configuration_sha256'] = sha(raw)
        report['cost_envelope'] = autonomy.price(dict(raw_input=raw.decode()),dict(document=p)); checkpoint()
        if not resume: store.append_bundle(study, actor, [dict(kind='protocols', record=workflow.protocol_record(p, protocol)),
            dict(kind='configurations', record=dict(id=uid(),identity='release-loopback',details=p['configurations'][0]['details'],input_versions=p['input_versions'],requested_resources=p['resource_limits'])),
            dict(kind='campaigns', record=dict(id=campaign,protocol_id=protocol,followup_of=None,title='Private bounded cloud TCP instrumentation control',stage='pilot',experiment_type='new-measurement',adapter=network_spec.VERSION,planned_units=1,coverage_limits=p['coverage_limits']))])
        source, claim, check = [str(uuid.uuid5(uuid.UUID(study), 'instrumentation-'+name)) for name in ('source','claim','check')]
        reviewer = dict(identity='Primary Codex AI implementer',type='AI',independence='Implementer; not independent or human review.')
        store.append_bundle(study, actor, [
            dict(kind='sources',record=dict(id=source,citation='Predeclared bounded TCP instrumentation control configuration',source_url=None,retrieved_url=None,
                kind='software-configuration',role='input-ground-truth',retrieved_version=sha(raw),sha256=sha(raw),byte_count=len(raw),access_status='retrieved',review_status='complete-review',
                review_definition='Examine every field of the complete canonical JSON control specification; this is not review of the cited academic paper.',
                examined='All fields of the fixed loopback specification: numeric payload/exchanges/delay, limits, metric names and units.',unexamined='none',
                retrieval_attempts=[dict(method='Reconstructed canonical specification compared byte-hash with retained frozen protocol and input identity.',at=workflow.now(),sha256=sha(raw))],
                reviewer=reviewer,findings='Fixed 32-byte payload, two exchanges and 2-ms application delay; expected received bytes 32 per exchange.',
                limitations='Locally generated software-control input; no paper claim, public Internet population, causal inference or independent replication.')),
            dict(kind='claims',record=dict(id=claim,source_id=source,location='Complete canonical loopback control specification',
                description='Each of two loopback exchanges receives exactly 32 payload bytes and records a finite nonnegative round-trip time in milliseconds.',claim_type='operational',
                scope=dict(kind='software-instrumentation-control',not_academic_paper_evidence=True,correlated_exchanges=2,independent_invocations=1),
                metrics=[dict(name='received_bytes',units='bytes'),dict(name='round_trip_time_ms',units='ms')],priority=3)),
            dict(kind='claim_checks',record=dict(id=check,claim_id=claim,campaign_id=campaign,method=network_spec.VERSION,applicability='applicable',
                rationale='Private predeclared software instrumentation check required for queue admission; no academic assessment is created.'))])
        report['software_control_claim_id'] = claim; report['academic_assessments_created'] = 0; checkpoint()
        request = dict(request_id=job,campaign_id=campaign,execution_mode='automatic',priority=3,dependencies=[],exclusive_resources=[],raw_input=raw.decode(),rationale='Service-operator software release control; no scientific assessment.',followup_of=None)
        report['queue_admission'] = scheduler.enqueue(study, actor, request); checkpoint()
        report['worker_invocation'] = release.prior.aws('lambda','invoke','--function-name',worker['arn'],'--payload','{}','--cli-binary-format','raw-in-base64-out','--cli-read-timeout','60',str(directory/'worker-response.json')); checkpoint()
        if report['worker_invocation'].get('FunctionError'): raise RuntimeError('Worker invocation failed; retained job must be inspected, not relaunched')
        for _ in range(12):
            row = store.rows('queue_jobs',dict(study_id='eq.'+study,id='eq.'+job))[0]
            if row['status'] not in ('queued','running'): break
            time.sleep(5)
        report['queue_outcome'] = dict(status=row['status'],reason=row['reason'],run_id=row['run_id']); checkpoint()
        if not row.get('run_id'): raise RuntimeError('No recorded run; retain pending identity without relaunch')
        run = store.rows('runs',dict(study_id='eq.'+study,id='eq.'+row['run_id']))[0]
        measurements = store.rows('measurements',dict(study_id='eq.'+study,run_id='eq.'+run['id']))
        if run['status'] != 'complete' or len(measurements) != 4: raise RuntimeError('Actual cloud measurement coverage differs')
        if sum(m['metric']=='received_bytes' and str(m['value'])=='32' and m['units']=='bytes' for m in measurements) != 2: raise RuntimeError('Payload byte/units invariant failed')
        if sum(m['metric']=='round_trip_time_ms' and m['units']=='ms' and math.isfinite(float(m['value'])) and float(m['value'])>=0 for m in measurements) != 2: raise RuntimeError('Timing units/bounds failed')
        (directory/'run.json').write_text(json.dumps(run,indent=2)+'\n'); (directory/'measurements.json').write_text(json.dumps(measurements,indent=2)+'\n')
        originals=[]
        for artifact in store.rows('artifacts',dict(study_id='eq.'+study)):
            original=store.artifact_bytes(study,artifact['id'],maximum=8000000)
            if sha(original)!=artifact['sha256']:raise RuntimeError('Remote artifact hash differs')
            (directory/('original-'+artifact['sha256'])).write_bytes(original)
            try:store.request('/storage/v1/object/'+store.BUCKET+'/'+artifact['storage_path'],public=True,raw=True)
            except store.StoreError as error:
                if not any('HTTP '+str(code) in str(error) for code in (400,401,403,404)):raise
            else:raise RuntimeError('Private control artifact is anonymously readable')
            originals.append(dict(id=artifact['id'],sha256=sha(original),bytes=len(original),provenance=artifact['provenance'],retrieved_hash_verified=True,anonymous_denied=True))
        if not any(a['provenance'].get('kind')=='bounded-tcp-original-lambda-response' for a in originals):raise RuntimeError('Original Lambda payload not retained')
        report.update(status='complete',measurements=4,originals=originals,run_id=run['id'],usage=run.get('usage'),automatic_paper_budget_admission=False,
            budget_scope='Fixed one-invocation operator control; atomic autonomous paper admission tested separately in SQL and the live trajectory.',
            conditional_gaps=['Google-authenticated browser launch not exercised by this operator control.'])
    except Exception as error:
        report.update(status='failed',reason=str(error));raise
    finally:
        report['ended_at']=dt.datetime.now(dt.timezone.utc).isoformat();checkpoint();print(json.dumps(dict(path=str(path),status=report['status'],reason=report.get('reason'))))


if __name__=='__main__':main()
