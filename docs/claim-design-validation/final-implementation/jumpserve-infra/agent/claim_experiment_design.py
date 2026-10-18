"""Bounded proposal formatting; model output never dispatches experiments."""
import hashlib
import json

VERSION = 'claim-experiment-design-v1'
MODULE = 'research-claim-design'
PROMPT_VERSION = 'research-claim-design-v3'
CHANNEL = 'submit_claim_experiment'
FIELDS = ('problem', 'question', 'hypothesis', 'conditions', 'related_work', 'alternatives',
          'design', 'metrics', 'controls', 'falsification', 'inputs', 'limitations')


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
    return dict(type=['object','null'],required=[key for key in properties if key!='execution'],properties=properties)


def response_channel():
    proposal = dict(type='object', additionalProperties=False, required=[*FIELDS, 'protocol'], properties={
        **{field: dict(type='string', maxLength=5000) for field in FIELDS},
        'protocol': protocol_schema()})
    schema = dict(type='object', additionalProperties=False, required=['summary', 'clarification_questions', 'proposal'], properties=dict(
        summary=dict(type='string', minLength=1, maxLength=4000),
        clarification_questions=dict(type='array', maxItems=3, items=dict(type='string', minLength=1, maxLength=1000)), proposal=proposal))
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


def parse(response, retained):
    blocks = response['output']['message']['content']
    if response.get('stopReason') != 'tool_use' or len(blocks) != 1 or set(blocks[0]) != {'toolUse'}:
        raise ValueError('Expected exactly one structured experimental proposal')
    channel = blocks[0]['toolUse']; value = channel.get('input')
    if channel.get('name') != CHANNEL or not isinstance(value, dict) or set(value) != {'summary', 'clarification_questions', 'proposal'}:
        raise ValueError('Unexpected proposal schema; no model-requested action is executed')
    if not isinstance(value['summary'], str) or not 1 <= len(value['summary'].strip()) <= 4000: raise ValueError('Bounded proposal summary required')
    if not isinstance(value['clarification_questions'], list) or len(value['clarification_questions']) > 3 or any(not isinstance(q, str) or not 1 <= len(q.strip()) <= 1000 for q in value['clarification_questions']): raise ValueError('Invalid proposal questions')
    plan = value['proposal']
    if not isinstance(plan, dict) or set(plan) != {*FIELDS, 'protocol'} or any(not isinstance(plan[field], str) or len(plan[field]) > 5000 for field in FIELDS): raise ValueError('Invalid plan fields')
    if len(canonical(plan)) > 24000 or plan['protocol'] is not None and not isinstance(plan['protocol'], dict): raise ValueError('Invalid candidate protocol or plan budget')
    if plan['hypothesis'] != retained['claim']['description']: raise ValueError('The proposal changed the paper claim')
    if plan['protocol'] is not None:
        if value['clarification_questions']: raise ValueError('Unresolved proposal questions require a draft without a candidate protocol')
        if plan['protocol'].get('hypotheses') != retained['claim']['description']: raise ValueError('Candidate protocol changed the paper hypothesis')
        source_sha = retained['source'].get('sha256')
        if source_sha and not any(isinstance(v, dict) and v.get('sha256') == source_sha for v in plan['protocol'].get('input_versions', [])): raise ValueError('Proposal dropped the original source hash')
        if plan['protocol'].get('execution') and not source_sha: raise ValueError('Automatic execution needs the original source identity')
    return dict(summary=value['summary'], questions=value['clarification_questions'], proposal=plan, findings=[], verdict='needs-clarification')
