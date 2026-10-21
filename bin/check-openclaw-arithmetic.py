"""Independent deterministic arithmetic check of the frozen IPv6 control inputs.

Predeclared software follow-up: compare every stored recorded cell to its exact
frozen observation/configuration/metric identity and Decimal value. Check percent
bounds, original panel tolerances, published identifiers, differences and labels.
Missing panels remain missing; disagreements are findings, not a failed campaign.
No inference intervals, seeds, new measurements, model calls or database writes.
Shares the archived source data and documented identifier format with the worker;
does not import its runner, compilation or numerical decision implementation.
Resource bound: six panels, 1152 cells, one local snapshot, at most 32 MB input.
"""
import argparse,datetime as dt,hashlib,json,uuid
from collections import Counter
from decimal import Decimal,localcontext
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda raw:hashlib.sha256(raw).hexdigest()
STUDY='5ef8e6bd-e3ff-4ba9-8427-d25fb525fb74'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--snapshot',required=True,type=Path);a=p.parse_args();path=a.snapshot.resolve()
 if not path.is_relative_to(ROOT/'.test-artifacts/openclaw-study-verification') or path.name!='private-snapshot.json' or path.stat().st_size>32000000:raise ValueError('Bounded retained control snapshot required')
 raw=path.read_bytes();data=json.loads(raw);assert {w['study_id'] for w in data['autonomy_workflows']}=={STUDY}
 original=(ROOT.parent/'jumpserve-back-end/research_workflow/plans/ipv6-archive-v1.json').read_bytes();plan=json.loads(original)
 assert sha(original)=='6bd31acb22a105c35ea9c54fa0a9381d0c5981bd554bed6443196b5eee3eebb3'
 prepared=uuid.uuid5(uuid.UUID(STUDY),'prepared:'+sha(original));panels=[];labels=Counter();count=0
 runs={r['id']:r for r in data['runs']};assert len(runs)==len(data['runs'])
 for c in plan['campaigns']:
  if c['execution_mode']!='automatic':continue
  job=str(uuid.uuid5(prepared,'job:'+c['key']));source=c['raw_input'].encode();inputs=json.loads(source,parse_float=Decimal)
  key=lambda r:tuple(r[n] for n in ('observation_id','configuration_identity','metric'))
  expected={key(v):v for v in inputs['observed']};published={key(v):v for v in inputs['published']}
  assert len(expected)==len(inputs['observed'])==len(published)==192
  if job not in runs:panels.append(dict(key=c['key'],job_id=job,status='not-recorded',required_cells=len(published),checked_cells=0));continue
  stored=[r for r in data['measurements'] if r['run_id']==job];actual={key(r):r for r in stored}
  assert len(stored)==len(actual)==192 and set(actual)==set(expected)==set(published)
  metrics={m['name']:m for m in c['protocol']['metrics']}
  for identity,row in actual.items():
   reference=published[identity];observation=expected[identity];spec=metrics[row['metric']]
   assert row['units']==reference['units']==observation['units']==spec['units']=='percent'
   assert row['status']==observation['status']=='recorded'
   value=Decimal(row['value']);expected_value=Decimal(str(observation['value']));published_value=Decimal(str(reference['value']))
   assert value.is_finite() and value==expected_value and Decimal(0)<=value<=Decimal(100)
   with localcontext() as ctx:ctx.prec=100;difference=value-published_value
   tolerance=Decimal(str(spec['tolerance_absolute']));label='reproduced' if abs(difference)<=tolerance else 'discrepant'
   assert Decimal(row['details']['difference'])==difference and Decimal(row['details']['published'])==published_value and Decimal(row['details']['tolerance_absolute'])==tolerance and row['details']['label']==label
   token=json.dumps(identity,separators=(',',':'))
   assert row['published_id']==str(uuid.uuid5(uuid.UUID(job),'published:'+token))
   assert row['id']==str(uuid.uuid5(uuid.UUID(job),'measurement:'+token))
   labels[label]+=1;count+=1
  panels.append(dict(key=c['key'],job_id=job,status=runs[job]['status'],required_cells=len(published),checked_cells=len(stored)))
 assert len(panels)==6 and count==len(data['measurements'])<=1152
 report=dict(version='openclaw-control-arithmetic-check-v1',checked_at=dt.datetime.now(dt.timezone.utc).isoformat(),status='passed',study_id=STUDY,snapshot_sha256=sha(raw),original_plan_sha256=sha(original),checker_sha256=sha(Path(__file__).read_bytes()),panels=panels,required_cells=1152,checked_cells=count,full_required_numerical_coverage=count==1152,labels=dict(labels),units='percent',model_calls=0,database_writes=0,new_empirical_measurements=0,uncertainty='Descriptive counts only; these reused deterministic cells do not support an inferential confidence interval.',reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),independence='Separate arithmetic implementation; shared frozen input data, UUID format, Python Decimal semantics and implementer. Not independent source-measurement or scientific validation.')
 target=path.parent/'arithmetic-report.json';target.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(report=str(target),checked_cells=count,required_cells=1152,labels=dict(labels)),indent=2))
if __name__=='__main__':main()
