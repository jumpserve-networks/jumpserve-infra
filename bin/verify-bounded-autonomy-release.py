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
    if len(sys.argv) != 1: raise RuntimeError('Fixed one-shot production control; no arbitrary arguments')
    BASE.mkdir(parents=True, exist_ok=True); path = BASE / 'report.json'
    if path.exists(): raise RuntimeError('Control already attempted; inspect retained identities, never relaunch')
    report = dict(status='running', protocol='autonomy-bounded-followups-release-protocol-v1',
        started_at=dt.datetime.now(dt.timezone.utc).isoformat(), reviewer=dict(identity='Primary Codex AI implementer', type='AI', independent=False),
        origin='Actual new TCP measurements inside the deployed Lambda; host-local instrumentation control, not Internet/CDN or paper-claim evidence.',
        actor='Service release operator; not a Google-authenticated browser action', new_model_calls=0, new_ec2_instances=0, measured_charges_usd=None)
    def checkpoint(): path.write_text(json.dumps(report, indent=2) + '\n')
    checkpoint()
    try:
        release.reviewed(); report['targets'] = release.prior.guard.target()
        functions = release.prior.functions(BASE, True)
        worker = next(f for f in functions if f['handler'] == 'worker.handler')
        config = release.prior.aws('lambda', 'get-function-configuration', '--function-name', worker['arn'])
        variables = config['Environment']['Variables']
        if variables['SUPABASE_URL'] != 'https://regphejnlvfpyokpniny.supabase.co': raise RuntimeError('Production target differs')
        os.environ.update(SUPABASE_URL=variables['SUPABASE_URL'], SUPABASE_SERVICE_ROLE_KEY=release.prior.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString'],
            SUPABASE_ANON_KEY=json.loads((ROOT/'cdk.json').read_bytes())['context']['supabaseAnonKey'], SSL_CERT_FILE='/etc/ssl/cert.pem',
            NETWORK_BOUNDED_FUNCTION=variables['NETWORK_BOUNDED_FUNCTION'], NETWORK_BOUNDED_POLICY_SHA256=variables['NETWORK_BOUNDED_POLICY_SHA256'])
        study, actor, protocol, campaign, job = [uid() for _ in range(5)]
        report.update(study_id=study, protocol_id=protocol, campaign_id=campaign, job_id=job); checkpoint()
        # A private auxiliary instrumentation campaign in the cited paper's
        # workspace; no source claim, assessment, publication or AI review is made.
        store.rpc('research_create_study',dict(p_actor=actor,p_id=study,p_document=workflow.paper_details(dict(title='Production bounded TCP instrumentation release verification',
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
        report['configuration'] = execution; report['configuration_sha256'] = sha(raw)
        report['cost_envelope'] = autonomy.price(dict(raw_input=raw.decode()),dict(document=p)); checkpoint()
        store.append_bundle(study, actor, [dict(kind='protocols', record=workflow.protocol_record(p, protocol)),
            dict(kind='configurations', record=dict(id=uid(),identity='release-loopback',details=p['configurations'][0]['details'],input_versions=p['input_versions'],requested_resources=p['resource_limits'])),
            dict(kind='campaigns', record=dict(id=campaign,protocol_id=protocol,followup_of=None,title='Private bounded cloud TCP instrumentation control',stage='pilot',experiment_type='new-measurement',adapter=network_spec.VERSION,planned_units=1,coverage_limits=p['coverage_limits']))])
        request = dict(request_id=job,campaign_id=campaign,execution_mode='automatic',priority=3,dependencies=[],exclusive_resources=[],raw_input=raw.decode(),rationale='Service-operator software release control; no scientific assessment.',followup_of=None)
        report['queue_admission'] = scheduler.enqueue(study, actor, request); checkpoint()
        report['worker_invocation'] = release.prior.aws('lambda','invoke','--function-name',worker['arn'],'--payload','{}','--cli-binary-format','raw-in-base64-out','--cli-read-timeout','60',str(BASE/'worker-response.json')); checkpoint()
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
        (BASE/'run.json').write_text(json.dumps(run,indent=2)+'\n'); (BASE/'measurements.json').write_text(json.dumps(measurements,indent=2)+'\n')
        originals=[]
        for artifact in store.rows('artifacts',dict(study_id='eq.'+study)):
            original=store.artifact_bytes(study,artifact['id'],maximum=8000000)
            if sha(original)!=artifact['sha256']:raise RuntimeError('Remote artifact hash differs')
            (BASE/('original-'+artifact['sha256'])).write_bytes(original)
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
