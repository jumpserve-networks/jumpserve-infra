"""Replay only passive delivery from fixed private retained original bytes."""
import copy,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'.test-artifacts/repair-closure-v1'
sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end'))
from platform_supervisor import working_evidence as evidence
from platform_supervisor.common import digest

def main():
 task=json.loads((BASE/'task.json').read_bytes());report=json.loads((BASE/'rebase-report.json').read_bytes());rows=json.loads((BASE/'artifacts.json').read_bytes())
 assert task['id']=='3ed262aa-e62f-4bed-9e35-d0be66c37150'
 assert report['plan_sha256']=='2e5074f011e5dfbadb2da4e89cad6a90d23687efd3582393a08fa099e8081f30'
 assert report['original_working_artifact']['sha256']=='3b655f6a068c9add6af6d245d37df4b01226016f76ff5fcfd875bf03923f492b'
 class Store:
  def __init__(self):self.task=dict(task,assessment_repair=True);self.reads=[]
  def rows(self,kind,**filters):
   assert kind=='artifacts';return [a for a in rows if a['sha256']==filters['sha256'][3:] and a['name']==filters['name'][3:]]
  def request(self,path,method='GET',body=None,raw=False):
   assert method=='GET' and body is None and raw and path.startswith('/storage/v1/object/platform-supervisor-private/'+task['id']+'/')
   self.reads.append(path);h=path.rsplit('/',1)[-1]
   a=next(a for a in rows if a['sha256']==h)
   value=(BASE/('original-checkpoint.bin' if h==report['original_working_artifact']['sha256'] else a['id']+'.bin')).read_bytes()
   assert digest(value)==h and len(value)==a['byte_count'];return value
 store=Store();state=copy.deepcopy(task['checkpoint']);state['working_evidence_contract']=evidence.VERSION
 class Controller:pass
 controller=Controller();controller.store=store;controller.state=state
 before=copy.deepcopy(state)
 with tempfile.TemporaryDirectory() as tmp:
  workspace=Path(tmp);(workspace/'rebase-conflicts.json').write_text(json.dumps(report))
  evidence.deliver(store,workspace,state);after=json.loads((workspace/'rebase-conflicts.json').read_bytes());local=after.pop('original_working_checkpoint')
  assert after==report and (workspace/local['path']).read_bytes()==(BASE/'original-checkpoint.bin').read_bytes()
  assert {k:v for k,v in state.items() if k!='working_evidence_seen'}==before and len(store.reads)==2
 result=dict(version='working-checkpoint-retained-control-v1',passed=True,task_id=task['id'],original_sha256=report['original_working_artifact']['sha256'],plan_sha256=report['plan_sha256'],original_bytes=local['bytes'],local_copy_delivered=True,original_report_and_source_binding_preserved=True,source_executed=False,provider_calls=0,production_mutations=0,reviewer='Primary implementing AI; not independent')
 (BASE/'retained-control-report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
