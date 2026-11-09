"""Read-only reproduction from fixed, previously hash-verified incident bytes.

No checkpoint source, helper or command is executed. Original paper/context and
native tool contents remain in ignored private local artifacts.
"""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end'))
sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
from platform_supervisor import incident_evidence,repair
import experiment_builder


def main():
    base=ROOT/'.test-artifacts/controller-handoff-v1'
    expected={
        'd3262f47-14f9-5d7c-905a-a4d564f1c1e2':'36343e305937114fe875257cfaba271ebc0d28a708475fb9b0310cb74c73a037',
        '73b6d207-de4e-52e9-add0-61933ecbb824':'69a3651a45422ad5308cae429b2509e1cb5ddd705463ef49376ed5bbbed43bfb',
    }
    originals={ident:(base/(ident+'.bin')).read_bytes() for ident in expected}
    assert all(hashlib.sha256(raw).hexdigest()==expected[ident] for ident,raw in originals.items())
    manifest=json.loads(originals['d3262f47-14f9-5d7c-905a-a4d564f1c1e2'])
    value=incident_evidence.checkpoint_view(originals['73b6d207-de4e-52e9-add0-61933ecbb824'])
    files=value['delivered_files'];declared={i['path']:i for i in manifest['files']}
    for name in ('finish-repair.py','work-packet.json','delivery-proofs.json','read-retained.py'):
        assert files[name]['original_sha256']==declared[name]['sha256'] and files[name]['original_bytes']==declared[name]['bytes']
    assert files['finish-repair.py']['original_sha256']==hashlib.sha256(experiment_builder.REPAIR_FINISH.encode()).hexdigest()
    history=value['native_history'];assert history['records']==504 and history['requests']==252
    assert history['shown_pairs']==8 and not history['complete'] and all(p['output_recorded'] for p in history['pairs'])
    # Redaction is the same boundary used by the actual supervisor delivery.
    projected,redaction=repair._project(value)
    assert projected['native_history']['original_sha256']==history['original_sha256']
    assert 'runtime_sources' not in manifest  # Historical absence stays explicit.
    report=dict(version='controller-handoff-retained-control-v1',passed=True,originals=expected,
        checkpoint_members_verified=4,native_history_records=history['records'],shown_paired_tool_records=history['shown_pairs'],
        original_completion_helper_present=True,helper_matches_retained_delivery_and_current_literal=True,
        historical_runtime_fingerprints_available=False,source_executed=False,provider_calls=0,production_mutations=0,
        redaction=redaction,scope='Original passive evidence delivery; no experiment, inference, assessment resumption or scientific validation.')
    path=base/'retained-control-report.json';path.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':main()
