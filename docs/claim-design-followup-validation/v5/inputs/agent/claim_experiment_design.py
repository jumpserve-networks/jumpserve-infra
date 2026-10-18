"""Bounded proposal formatting; model output never dispatches experiments."""
import hashlib
import json
import copy
import re
from pathlib import Path

VERSION = 'claim-experiment-design-v1'
MODULE = 'research-claim-design'
PROMPT_VERSION = 'research-claim-design-v5'
RESPONSE_VERSION = 'claim-design-response-v2'
CHANNEL = 'submit_claim_experiment'
FIELDS = ('problem', 'question', 'hypothesis', 'conditions', 'related_work', 'alternatives',
          'design', 'metrics', 'controls', 'falsification', 'inputs', 'limitations')
MODEL_FIELDS = tuple(field for field in FIELDS if field != 'falsification')
POLICY_BYTES = Path(__file__).with_name('claim-decision-policy-v1.json').read_bytes()
POLICY = json.loads(POLICY_BYTES)
POLICY_SHA256 = hashlib.sha256(POLICY_BYTES).hexdigest()
RUNNER_CONTEXT = dict(version='claim-runner-context-v1',origin='server-code-contract',
    builtin_metrics={'emulated-netem-v1':{'flow_completion_time_ms':'ms'},
        'real-world-iperf-v1':{'throughput_mbit_s':'Mbit/s','received_bytes':'bytes','duration_seconds':'s','rtt_median_ms':'ms','retransmits':'count'}},
    definitions=dict(flow_completion_time_ms='Elapsed time for a flow to complete, recorded in ms. This is not a one-way delay or a round-trip time.',
        delay_placement='A delay value in ms alone does not specify one-way versus round-trip placement. Use explicit source/owner declarations and the specific script/topology semantics; otherwise ask.',
        seeds='Do not assert an emulation seed or default value when none is supplied.'),
    scope_limits=['Built-in netem and iperf runners measure packet transport; neither implements an orbital, optical-terminal, atmospheric or physical-availability model.',
        'Packet success, transport loss or uptime cannot be substituted for optical-terminal availability without an applicable, supplied and reviewed model.',
        'A custom package needs its actual version/digest and applicable implementation; no package identity or specialist model is implied by a runner name.',
        'Runner metric contracts describe supported outputs, not credential, hardware or deployment availability.',
        'Only recorded metadata is supplied here. Full text not included in a model call is not proof that it is unavailable elsewhere.'])


def planning_context():
    return dict(decision_policy=dict(POLICY,sha256=POLICY_SHA256,origin='server-policy',model_authored=False),
        runner_context=copy.deepcopy(RUNNER_CONTEXT))


def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def protocol_schema():
    bounded = dict(type='string', minLength=1, maxLength=4000)
    strings = dict(type='array', minItems=1, maxItems=20, items=bounded)
    applicability = dict(type='object', additionalProperties=False, required=['applicable','rationale'], properties=dict(applicable=dict(type='boolean'),rationale=bounded))
    properties = {key:bounded for key in ('hypotheses','dates_or_epochs','replication_unit','sample_size_rationale','exclusions','missing_data','statistics','dependence','stopping_rule','prior_exposure','coverage_limits')}
    properties.update(questions=strings,algorithms=strings,controls=strings,seeds=applicability,sensitivity=applicability,
        planned_units=dict(type='integer',minimum=1,maximum=10000),
        stage=dict(type='string',enum=['pilot','main']),experiment_type=dict(type='string',enum=['new-measurement','independent-check','broader-validation']),
        data_origin=dict(type='string',enum=['archived-data','new-empirical','simulation','model-output','software-fixture','mixed','unclassified']),
        metrics=dict(type='array',minItems=1,maxItems=20,items=dict(type='object',required=['name','units'],properties=dict(name=dict(type='string'),units=dict(type='string'),lower_bound=dict(type='number'),upper_bound=dict(type='number'),criterion=bounded))),
        configurations=dict(type='array',minItems=1,maxItems=32,items=dict(type='object',required=['identity','details'],properties=dict(identity=dict(type='string',maxLength=300),details=dict(type='object',properties=dict(test_config=dict(type='object')))))),
        input_versions=dict(type='array',minItems=1,maxItems=64,items=dict(type='object',required=['identity','sha256'],properties=dict(identity=dict(type='string',maxLength=300),sha256=dict(type='string',pattern='^[a-f0-9]{64}$')))),
        resource_limits=dict(type='object',required=['max_observations','max_input_bytes','wall_seconds','estimated_cost_usd','cost_basis'],properties=dict(max_observations=dict(type='integer',minimum=1,maximum=10000),max_input_bytes=dict(type='integer',minimum=1,maximum=10000000),wall_seconds=dict(type='integer',minimum=1,maximum=3600),estimated_cost_usd=dict(type=['number','null']),cost_basis=bounded)),
        execution=dict(type=['object','null'],additionalProperties=False,required=['version','runner','replications','limits','exclusive_resources'],properties=dict(version=dict(type='string',enum=['network-execution-v1']),runner=dict(type='string',enum=['emulated-netem-v1','real-world-iperf-v1','custom-package-v1']),replications=dict(type='integer',minimum=1,maximum=32),exclusive_resources=dict(type='array',maxItems=16,items=dict(type='string')),limits=dict(type='object',additionalProperties=False,required=['wall_seconds','max_instances','max_output_bytes','max_network_bytes'],properties=dict(wall_seconds=dict(type='integer',minimum=60,maximum=3600),max_instances=dict(type='integer',minimum=1,maximum=18),max_output_bytes=dict(type='integer',minimum=1024,maximum=10000000),max_network_bytes=dict(type='integer',minimum=1024,maximum=10000000000))))))
    # Decision rules are server-owned; the model cannot return inferential prose
    # in either protocol.statistics or metric decision thresholds.
    properties.pop('statistics')
    properties['metrics']['items']['properties'].pop('criterion')
    properties['stage']['enum'] = ['pilot']
    return dict(type='object',additionalProperties=False,required=[key for key in properties if key!='execution'],properties=properties)


def response_channel():
    proposal = dict(type='object', additionalProperties=False, required=[*MODEL_FIELDS, 'protocol'], properties={
        **{field: dict(type='string', maxLength=5000) for field in MODEL_FIELDS},
        'protocol': protocol_schema()})
    schema = dict(type='object', additionalProperties=False, required=['mode', 'summary', 'clarification_questions', 'proposal'], properties=dict(
        mode=dict(type='string',enum=['clarify','propose','reuse']),summary=dict(type='string', minLength=1, maxLength=2000),
        clarification_questions=dict(type='array', maxItems=3, items=dict(type='string', minLength=1, maxLength=1000)),
        proposal=dict(anyOf=[dict(type='null'),proposal])))
    return dict(tools=[dict(toolSpec=dict(name=CHANNEL, description='Return a source-bound experimental proposal. Formatting only; no experiment is executed.', inputSchema=dict(json=schema)))], toolChoice=dict(tool=dict(name=CHANNEL)))


def retained_context(row):
    raw = row['raw_document'].encode()
    if hashlib.sha256(raw).hexdigest() != row['sha256'] or json.loads(raw) != row['document']:
        raise ValueError('Original claim context bytes differ from their retained hash')
    origin = row['document']; source = origin['source']
    # Explicit metadata projection: no arbitrary URL fetch and no implied full-text read.
    return dict(context_sha256=row['sha256'], original_study_id=origin['study']['id'], claim=origin['claim'], gap=origin['gap'],
        source={key: source.get(key) for key in ('citation', 'source_url', 'retrieved_version', 'sha256', 'access_status', 'review_status', 'examined', 'unexamined', 'findings', 'limitations')},
        coverage='Recorded claim/source metadata only. Original full text and artifacts are not fetched by this model call.')


def parse(response, retained, packet=None):
    blocks = response['output']['message']['content']
    if response.get('stopReason') != 'tool_use' or len(blocks) != 1 or set(blocks[0]) != {'toolUse'}:
        raise ValueError('Expected exactly one structured experimental proposal')
    channel = blocks[0]['toolUse']; value = channel.get('input')
    if channel.get('name') != CHANNEL or not isinstance(value, dict) or set(value) != {'mode','summary', 'clarification_questions', 'proposal'}:
        raise ValueError('Unexpected proposal schema; no model-requested action is executed')
    if not isinstance(value['summary'], str) or not 1 <= len(value['summary'].strip()) <= 2000: raise ValueError('Bounded planning summary required')
    if not isinstance(value['clarification_questions'], list) or len(value['clarification_questions']) > 3 or any(not isinstance(q, str) or not 1 <= len(q.strip()) <= 1000 for q in value['clarification_questions']): raise ValueError('Invalid proposal questions')
    mode=value['mode'];reused=mode=='reuse'
    if mode not in ('clarify','propose','reuse'): raise ValueError('Choose a supported planning response mode')
    if mode=='clarify':
        if value['proposal'] is not None or not value['clarification_questions']:
            raise ValueError('Clarification needs concrete questions and no proposal; unresolved information cannot become a plan')
        plan=None
    else:
        if value['clarification_questions']: raise ValueError('Resolve questions before returning a candidate protocol')
        original = (packet or {}).get('protocol')
        if reused:
            if value['proposal'] is not None: raise ValueError('Reuse references the saved packet; model reconstruction is not accepted')
            if not isinstance(original, dict): raise ValueError('No saved protocol to reference')
            # Only an already descriptive pilot can use this shortcut. The owner
            # must first save explicit descriptive scope; the model cannot turn
            # an inferential plan into a descriptive one by reference.
            stats = original.get('statistics', '').lower()
            if original.get('stage') != 'pilot' or not ('descriptive' in stats or re.search(r'\bno (?:\w+\s+){0,5}(?:inferential|population)\b',stats)):
                raise ValueError('Protocol references require an explicitly descriptive saved pilot')
            plan = copy.deepcopy(packet)
        else:
            plan=copy.deepcopy(value['proposal'])
            if not isinstance(plan,dict) or set(plan)!={*MODEL_FIELDS,'protocol'} or any(not isinstance(plan[field],str) or len(plan[field])>5000 for field in MODEL_FIELDS):
                raise ValueError('Invalid plan fields; decision rules are supplied by the server')
            if not isinstance(plan['protocol'],dict): raise ValueError('A proposal requires a complete candidate protocol; otherwise ask clarifying questions')
            if any(key in plan['protocol'] for key in ('statistics', 'decision_policy')):
                raise ValueError('The model cannot supply a statistical decision policy')
            if any(any(key in metric for key in ('criterion','tolerance_absolute','tolerance_relative')) for metric in plan['protocol'].get('metrics', []) if isinstance(metric,dict)):
                raise ValueError('Model-supplied decision thresholds need a separately reviewed analysis design')
        if plan['hypothesis'] != retained['claim']['description']: raise ValueError('The proposal changed the paper claim')
        if plan['protocol'].get('stage') != 'pilot': raise ValueError('The automatic designer supports descriptive pilots; main inference needs a reviewed domain design')
        if isinstance(original, dict):
            for key in ('configurations','execution','planned_units','resource_limits','input_versions'):
                if canonical(plan['protocol'].get(key)) != canonical(original.get(key)):
                    raise ValueError('AI proposal changed saved '+key+'; explicitly edit and save the owner plan before requesting fresh reviews')
        if plan['protocol'].get('hypotheses') != retained['claim']['description']: raise ValueError('Candidate protocol changed the paper hypothesis')
        source_sha = retained['source'].get('sha256')
        if source_sha and not any(isinstance(v, dict) and v.get('sha256') == source_sha for v in plan['protocol'].get('input_versions', [])): raise ValueError('Proposal dropped the original source hash')
        if plan['protocol'].get('execution') and not source_sha: raise ValueError('Automatic execution needs the original source identity')
        plan['protocol']['statistics'] = POLICY['statistics']
        plan['protocol']['decision_policy'] = dict(version=POLICY['version'], sha256=POLICY_SHA256, mode=POLICY['mode'])
        plan['falsification'] = POLICY['decision_rule']
    if len(canonical(plan)) > 24000: raise ValueError('Compiled proposal exceeds the retained packet budget')
    return dict(response_version=RESPONSE_VERSION,response_mode=mode,summary=value['summary'], questions=value['clarification_questions'], proposal=plan, findings=[], verdict='needs-clarification',
        decision_policy=dict(version=POLICY['version'],sha256=POLICY_SHA256,mode=POLICY['mode'],origin='server-policy',
            model_authored=False,fields=['/proposal/falsification','/proposal/protocol/statistics','/proposal/protocol/decision_policy'] if plan else [],
            protocol_reused=reused,raw_model_proposal_sha256=hashlib.sha256(canonical(value['proposal'])).hexdigest()))
