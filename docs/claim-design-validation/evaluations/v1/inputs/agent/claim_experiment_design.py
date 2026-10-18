"""Bounded proposal formatting; model output never dispatches experiments."""
import hashlib
import json

VERSION = 'claim-experiment-design-v1'
MODULE = 'research-claim-design'
PROMPT_VERSION = 'research-claim-design-v1'
CHANNEL = 'submit_claim_experiment'
FIELDS = ('problem', 'question', 'hypothesis', 'conditions', 'related_work', 'alternatives',
          'design', 'metrics', 'controls', 'falsification', 'inputs', 'limitations')


def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def response_channel():
    proposal = dict(type='object', additionalProperties=False, required=[*FIELDS, 'protocol'], properties={
        **{field: dict(type='string', maxLength=5000) for field in FIELDS},
        'protocol': dict(type=['object', 'null'])})
    schema = dict(type='object', additionalProperties=False, required=['summary', 'questions', 'proposal'], properties=dict(
        summary=dict(type='string', minLength=1, maxLength=4000),
        questions=dict(type='array', maxItems=3, items=dict(type='string', minLength=1, maxLength=1000)), proposal=proposal))
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
    if channel.get('name') != CHANNEL or not isinstance(value, dict) or set(value) != {'summary', 'questions', 'proposal'}:
        raise ValueError('Unexpected proposal schema; no model-requested action is executed')
    if not isinstance(value['summary'], str) or not 1 <= len(value['summary'].strip()) <= 4000: raise ValueError('Bounded proposal summary required')
    if not isinstance(value['questions'], list) or len(value['questions']) > 3 or any(not isinstance(q, str) or not 1 <= len(q.strip()) <= 1000 for q in value['questions']): raise ValueError('Invalid proposal questions')
    plan = value['proposal']
    if not isinstance(plan, dict) or set(plan) != {*FIELDS, 'protocol'} or any(not isinstance(plan[field], str) or len(plan[field]) > 5000 for field in FIELDS): raise ValueError('Invalid plan fields')
    if len(canonical(plan)) > 24000 or plan['protocol'] is not None and not isinstance(plan['protocol'], dict): raise ValueError('Invalid candidate protocol or plan budget')
    if plan['hypothesis'] != retained['claim']['description']: raise ValueError('The proposal changed the paper claim')
    if plan['protocol'] is not None:
        source_sha = retained['source'].get('sha256')
        if source_sha and not any(isinstance(v, dict) and v.get('sha256') == source_sha for v in plan['protocol'].get('input_versions', [])): raise ValueError('Proposal dropped the original source hash')
        if plan['protocol'].get('execution') and not source_sha: raise ValueError('Automatic execution needs the original source identity')
    return dict(summary=value['summary'], questions=value['questions'], proposal=plan, findings=[], verdict='needs-clarification')
