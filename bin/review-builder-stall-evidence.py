"""Read-only correctness checks and CSV export; not a scientific verdict/review."""
import csv,datetime as dt,hashlib,io,json,math,pathlib,statistics,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
sha=lambda raw:hashlib.sha256(raw).hexdigest()

def main():
 base=ROOT/'.test-artifacts/builder-stall-release-v1';source=base/(base/'selected.txt').read_text().strip();frozen=json.loads((source/'frozen.json').read_bytes());live=json.loads((source/'live.json').read_bytes())
 assert live['status']=='awaiting-substantive-review' and live['actual_calls']==0 and live['inherited_actual_calls']==46
 assert all(c['structural_checks_passed'] for c in live['cases'])
 raw=(source/'evidence.zip').read_bytes();pointer=json.loads((source/'host-status.json').read_bytes())['evidence.json'];assert sha(raw)==pointer['sha256']
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  for entry in json.loads(z.read('artifact-manifest.json')):assert sha(z.read(entry['path']))==entry['sha256']
 case=next(c for c in live['cases'] if c['name']=='full-grid-netem');assert len(case['replications'])==3
 units={'throughput_mbit_s':'Mbit/s','received_bytes':'bytes','duration_seconds':'s','idle_rtt_ms':'ms','retransmits':'count'};losses=[0,1,2,5,10];exports=[];checks=[];values={loss:[] for loss in losses}
 for index,run in enumerate(case['replications']):
  assert run['replication']==index and dt.datetime.fromisoformat(run['ended_at'])>=dt.datetime.fromisoformat(run['started_at'])
  out=run['output'];rows=out['observations'];producer=out['provenance'];config=producer['requested']
  assert config==dict(cca='cubic',loss_levels_pct=losses,rate_mbit=100,one_way_delay_ms=20,duration_seconds=30,queue_packets=1000,mtu=1500,socket_buffer_bytes=131072,seed=773,loss_seed=None,ping_count=3)
  assert producer['implementation_sha256']==frozen['runtime_manifest']['files']['netem_iperf.py'] and producer['data_origin']=='new-empirical'
  matched={(r['observation_key'],r['metric']):r for r in rows};assert len(rows)==len(matched)==25 and set(matched)=={('loss:'+str(loss),m) for loss in losses for m in units}
  commands=[c for c in producer['commands'] if 'iperf3' in c['argv'] and '-c' in c['argv']];assert len(commands)==5
  for loss,command in zip(producer['condition_order'],commands):
   assert command['returncode']==0;iperf=json.loads(command['stdout']);assert not iperf.get('error');rx=iperf['end']['sum_received'];throughput=8*rx['bytes']/rx['seconds']/1_000_000
   row=matched[('loss:'+str(loss),'throughput_mbit_s')];assert row['status']=='recorded' and math.isclose(row['value'],throughput,rel_tol=1e-9,abs_tol=1e-8)
   assert math.isclose(throughput*1_000_000,rx['bits_per_second'],rel_tol=1e-6,abs_tol=1)
   assert matched[('loss:'+str(loss),'received_bytes')]['value']==rx['bytes'] and matched[('loss:'+str(loss),'duration_seconds')]['value']==rx['seconds']
   values[loss].append(throughput)
  for r in rows:
   assert r['units']==units[r['metric']] and r['metadata']['replication']==index
   if r['status']=='recorded':assert type(r['value']) in (int,float) and math.isfinite(r['value']) and r['value']>=0
   else:assert r['value'] is None and r['reason'] and r['status'] in ('missing','invalid','ambiguous')
   exports.append(dict(replication=index,loss_pct=r['metadata']['loss_pct'],metric=r['metric'],units=r['units'],value=r['value'],status=r['status'],reason=r['reason'],started_at_utc=run['started_at'],ended_at_utc=run['ended_at'],data_origin='new-empirical',scope='repeated-host software qualification',original_stdout_sha256=run['sha256'],implementation_sha256=producer['implementation_sha256']))
  checks.append(dict(replication=index,observations=25,independent_rate_comparisons=5,configuration_preserved=True))
 path=source/'netem-observations.csv'
 with path.open('w',newline='') as sink:
  writer=csv.DictWriter(sink,fieldnames=list(exports[0]));writer.writeheader();writer.writerows(exports)
 counts={status:sum(r['status']==status for r in exports) for status in ('recorded','missing','invalid','ambiguous')}
 summary=[dict(loss_pct=loss,n=len(v),mean_mbit_s=statistics.mean(v),min_mbit_s=min(v),max_mbit_s=max(v),range_type='descriptive; not a confidence interval') for loss,v in values.items()]
 report=dict(version='builder-stall-independent-checks-v1',status='passed',source_revision=frozen['source_revision'],checks=checks,counts=counts,throughput=summary,csv=dict(path=str(path.relative_to(ROOT)),sha256=sha(path.read_bytes()),rows=len(exports)),shared_assumptions='Independent calculation code uses the same captured iperf counters and configurations. It cannot establish correctness of iperf/kernel clocks, causality, external-network validity or generalization.',dependence='Three repeated trials share one host; no independent-host population or confidence interval.',scientific_verdict=None,reviewer=dict(identity='Codex implementing AI',type='AI',independent=False,human=False,held_out=False),scope='Deterministic support for substantive AI inspection, not automatic review completion.')
 (source/'independent-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
