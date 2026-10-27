"""Fixed TCP88 development replay; local evidence only, no database writes/deploys.

Freeze before run. Uses a previously acquired, private read-only assessment
snapshot and native OpenClaw subscription authorization. No paid API fallback.
"""
import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BACK = ROOT.parent / 'jumpserve-back-end'
ASSESSMENT = 'd9161d19-7733-4b8b-92cf-74804d63da7b'
SNAPSHOT_SHA = '0bd7a61dbe93a520ac6d37cadc9ca935622e6b33604dd0ae4291d915b0604ba4'
PAPER_SHA = '9ca88dfa60f98d5cf736c3917df45420eb91861dd1de453a3dedf3d91c1836eb'
BASE = ROOT / '.test-artifacts/tcp88-selection'
sys.path.insert(0, str(BACK / 'research_workflow'))
os.environ['RESEARCH_AI_RUNTIME'] = 'openclaw-production-v1'
os.environ.setdefault('OPENCLAW_NODE', str(BACK / 'experiments/openclaw_pilot/runtime/node_modules/node/bin/node'))
os.environ.setdefault('OPENCLAW_PACKAGE', str(BACK / 'experiments/openclaw_pilot/runtime/node_modules/openclaw'))
os.environ.setdefault('OPENCLAW_AUTH_DIR', str(BACK / 'experiments/openclaw_pilot/.subscription-auth'))
import autonomy_model as model
import openclaw_runtime as runtime
import paper_selection as selection
from workflow import canonical, digest, now


def freeze():
    snapshots = [p for p in (ROOT / '.test-artifacts/tcp88-extraction').glob('*/private-assessment-snapshot.json') if digest(p.read_bytes()) == SNAPSHOT_SHA]
    if len(snapshots) != 1:
        raise ValueError('Exactly one original, hash-verified read-only snapshot is required.')
    snapshot = snapshots[0]
    data = json.loads(snapshot.read_bytes())
    assert data['review']['study_id'] == ASSESSMENT
    assert any(a['sha256'] == PAPER_SHA and a['provenance']['kind'] == 'paper-original-upload' for a in data['artifacts'])
    claims = sorted(data['claims'], key=lambda c: (c['created_at'], c['id']))
    values = selection.candidates(claims, data['review']['seeds'])
    contexts = [json.loads(t['request']['messages'][0]['content'][0]['text']) for t in data['turns']]
    for c in claims:
        assert any(x.get('source_chunk', {}).get('page') == c['scope']['source_page'] and c['description'] in x['source_chunk']['text'] for x in contexts)
    assert len(values) == 175
    original_request = data['turns'][0]['request']
    system = original_request['system'][0]['text']
    directory = BASE / dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True, mode=0o700)
    packet = dict(version='tcp88-selection-development-v1', frozen_at=now(), assessment_id=ASSESSMENT,
        classification='Exposed real-paper development replay; not held-out validation or an experiment reproducing scientific claims.',
        input=dict(snapshot=str(snapshot.relative_to(ROOT)), snapshot_sha256=SNAPSHOT_SHA, paper_sha256=PAPER_SHA,
            version='Jacobson and Karels, Congestion Avoidance and Control, November 1988, 25 PDF pages',
            source_url='https://www.cs.princeton.edu/courses/archive/fall17/cos561/papers/TCP88.pdf'),
        candidates=values, system=system, system_sha256=digest(system.encode()),
        prompt_version_id=data['turns'][0]['prompt_version_id'], model_id=runtime.MODEL,
        policy_sha256=digest(canonical(selection.POLICY)),
        implementation_sha256={n:digest((BACK / 'research_workflow' / n).read_bytes()) for n in ('paper_selection.py','autonomy_model.py','openclaw_runtime.py','openclaw_auth.mjs','siwc_protocol.py','policies/paper-review-selection-v1.json')},
        producer_sha256=digest(Path(__file__).read_bytes()),
        limits=dict(maximum_calls=22,maximum_elapsed_seconds=1200,maximum_request_bytes=96000,paid_fallback=False,maximum_orchestration_reservation_cents=2200),
        exclusions='None of the 175 retained candidates excluded. Figures, tables, original code and supplements are outside this replay.',
        stopping='Stop at first provider/structural failure or resource limit; retain all original requests and answers. No automatic repair retries.',
        pass_criteria=['Every candidate reaches exactly one full-text batch, unchanged.', 'Every answer passes actual controller phase and selected-ID validation.',
            'Final suggestions include at least one central claim and three findings for this known algorithmic paper; no invented minimum applies in production.',
            'AI implementer separately inspects final original statements and labels for meaningful categories, conditions, units and duplicates; this is not independent or human review.'],
        inference='Descriptive software/development check. No statistical confidence interval or scientific reproduction claim is justified.',
        reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),
        measured_charges_usd=None,subscription_allocation_usd=None)
    (directory/'frozen.json').write_bytes(canonical(packet))
    (BASE/'selected.txt').write_text(directory.name+'\n')
    print(json.dumps(dict(directory=str(directory),candidates=len(values),maximum_calls=22,model_calls=0)))


def run():
    name=(BASE/'selected.txt').read_text().strip()
    if not name.endswith('Z') or not name[:-1].replace('T','').isdigit():
        raise ValueError('Invalid frozen replay identity.')
    directory=BASE/name
    packet=json.loads((directory/'frozen.json').read_bytes())
    path=directory/'evaluation.json'
    if path.exists():
        raise ValueError('Preserve the original run; freeze a new version before any follow-up.')
    assert digest(Path(__file__).read_bytes()) == packet['producer_sha256']
    for n,sha in packet['implementation_sha256'].items():
        assert digest((BACK/'research_workflow'/n).read_bytes()) == sha
    start=packet.get('starting_cursor',0)
    result=dict(version=packet['version'],started_at=now(),status='running',calls=[],seen_ids=[c['id'] for c in packet['candidates'][:start]],cursor=start,
        reviewer=packet['reviewer'],read_only_production=True,model_id=runtime.MODEL,
        measured_charges_usd=None,subscription_allocation_usd=None,paid_fallback=False,
        raw_answer_reviewed=False,limitations=packet['classification'])
    save=lambda:path.write_bytes(canonical(result))
    save();began=time.monotonic();previous=packet.get('starting_shortlist',{})
    try:
        runtime.verify_runtime()
        while result['cursor'] < len(packet['candidates']):
            if len(result['calls'])>=packet['limits']['maximum_calls'] or time.monotonic()-began>=packet['limits']['maximum_elapsed_seconds']-150:
                raise ValueError('Frozen replay resource bound reached.')
            context=selection.context(dict(title='Congestion Avoidance and Control'),packet['candidates'],result['cursor'],previous)
            logical=model.request(packet['system'],context)
            if len(canonical(logical))>packet['limits']['maximum_request_bytes']:
                raise ValueError('Complete request exceeds byte limit; no truncation or call.')
            number=len(result['calls'])+1
            entry=dict(number=number,status='admitted',cursor=result['cursor'],candidate_ids=[c['id'] for c in context['candidates']],
                request_sha256=digest(canonical(logical)),reserved_orchestration_cents=100)
            result['calls'].append(entry);save()
            answer,receipt=runtime.execute(logical,directory/('turn-'+str(number)))
            entry.update(status=receipt['status'],receipt=receipt);save()
            if not answer:
                raise ValueError('Provider answer unavailable; preserve attempt without retry.')
            output=model.parse(answer);model.validate_phase(output,context)
            if output['action']!='discover':
                raise ValueError('Replay must return discovery/organization, not a scientific verdict.')
            allowed={c['id'] for c in context['candidates']}|{c['claim_id'] for g in selection.GROUPS for c in previous.get(g,[])}
            previous=selection.validate(output.get('paper_review_selection'),allowed)
            (directory/('turn-'+str(number))/'parsed.json').write_bytes(canonical(output))
            result['seen_ids'].extend(entry['candidate_ids']);result['cursor']+=len(context['candidates'])
            result['suggestions']=previous;entry['structural_passed']=True;save()
            print(json.dumps(dict(turn=number,cursor=result['cursor'],central=len(previous['central_claims']),findings=len(previous['testable_findings']))),flush=True)
        assert result['seen_ids']==[c['id'] for c in packet['candidates']]
        assert len(previous['central_claims'])>=1 and len(previous['testable_findings'])>=3
        result['status']='awaiting-substantive-AI-review'
    except Exception as error:
        result.update(status='failed-or-paused',reason=type(error).__name__+': '+str(error)[:500])
        raise
    finally:
        result.update(ended_at=now(),wall_seconds=time.monotonic()-began)
        save()
        print(json.dumps(dict(directory=str(directory),status=result['status'],cursor=result['cursor'],calls=len(result['calls']))))


def freeze_followup():
    name=(BASE/'selected.txt').read_text().strip()
    if not name.endswith('Z') or not name[:-1].replace('T','').isdigit():
        raise ValueError('Invalid parent replay identity.')
    parent=BASE/name
    original=json.loads((parent/'frozen.json').read_bytes())
    result=json.loads((parent/'evaluation.json').read_bytes())
    if original['version']!='tcp88-selection-development-v1' or result['status']!='failed-or-paused' or result['cursor']!=136 or result['calls'][-1]['receipt']['error_code']!='server_is_overloaded':
        raise ValueError('Only the retained, observed overload can admit this follow-up.')
    if digest((parent/'evaluator-original.py').read_bytes())!=original['producer_sha256']:
        raise ValueError('Preserve the original evaluator bytes before amendment.')
    directory=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(mode=0o700)
    packet=dict(original,version='tcp88-selection-development-followup-v1',frozen_at=now(),
        producer_sha256=digest(Path(__file__).read_bytes()),
        parent=dict(directory=str(parent.relative_to(ROOT)),protocol_sha256=digest((parent/'frozen.json').read_bytes()),result_sha256=digest((parent/'evaluation.json').read_bytes())),
        starting_cursor=result['cursor'],starting_shortlist=result['suggestions'],
        amendment='Observed provider server_is_overloaded after 136 candidates. Resume the remaining 39 unchanged candidates and prior shortlist; no prompt/policy changes. This is a dependent operational continuation, not independent validation.',
        limits=dict(maximum_calls=5,maximum_elapsed_seconds=480,maximum_request_bytes=96000,paid_fallback=False,maximum_orchestration_reservation_cents=500),
        stopping='Stop on the first further provider/structural failure or resource limit. No automatic retry.',
        aggregate_limits=dict(maximum_provider_attempts=23,maximum_orchestration_reservation_cents=2300))
    (directory/'frozen.json').write_bytes(canonical(packet))
    (directory/'evaluator-original.py').write_bytes(Path(__file__).read_bytes())
    (BASE/'selected.txt').write_text(directory.name+'\n')
    print(json.dumps(dict(directory=str(directory),starting_cursor=136,remaining_candidates=39,maximum_calls=5,model_calls=0)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['freeze-tcp88','freeze-follow-up','run'])
    args=parser.parse_args()
    if args.mode=='freeze-tcp88':freeze()
    elif args.mode=='freeze-follow-up':freeze_followup()
    else:run()
