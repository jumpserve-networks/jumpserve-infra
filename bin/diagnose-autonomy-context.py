"""Fixed-target read-only diagnosis of the latest matching 96 KB claim pause.

Does not invoke models, change prompts, resume tasks or deploy resources. Private
source/context bytes are retained only in the ignored local evidence directory.
"""
import datetime as dt, importlib.util, json, os, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('context_release_guard',ROOT/'bin/autonomy-release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
sys.path.insert(0,str(ROOT.parent/'jumpserve-back-end/research_workflow'))
import autonomy, autonomy_model as model
from workflow import canonical,digest

def main():
 directory=ROOT/'.test-artifacts/autonomy-context-diagnostic'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
 report=dict(read_only=True,new_model_calls=0,measured_charges_usd=None,status='running')
 try:
  report['targets']=release.guard.target()
  tasks=release.admin.query("select * from research_autonomy_tasks where status='blocked' and stage in ('planning','assessment') and reason='Autonomous context exceeds 96 KB; retain explicit coverage rather than truncate evidence.' order by updated_at desc,id limit 1")
  if not tasks:report.update(status='no-matching-task');return
  task=tasks[0];task['workflow']=release.admin.query('select * from research_autonomy_workflows where study_id='+release.admin.literal(task['study_id'])+'::uuid')[0]
  report.update(study_id=task['study_id'],task_id=task['id'],stage=task['stage'],attempts=task['attempts'])
  if sys.platform=='darwin':os.environ.setdefault('SSL_CERT_FILE','/etc/ssl/cert.pem')
  os.environ['SUPABASE_URL']='https://regphejnlvfpyokpniny.supabase.co'
  os.environ['SUPABASE_SERVICE_ROLE_KEY']=release.aws('secretsmanager','get-secret-value','--secret-id','jumpserve/supabase-service-key')['SecretString']
  prompt,system=model.load_prompt();context=autonomy.build_context(task)
  (directory/'context.json').write_bytes(canonical(context));(directory/'system.txt').write_text(system)
  try:value=model.request(system,context);request_bytes=len(canonical(value));error=None
  except ValueError as exc:request_bytes=None;error=str(exc)
  report.update(status='complete',study_id=task['study_id'],task_id=task['id'],stage=task['stage'],attempts=task['attempts'],prompt_id=prompt['id'],context_sha256=digest(canonical(context)),context_bytes=len(canonical(context)),field_bytes={k:len(canonical(v)) for k,v in context.items()},request_bytes=request_bytes,request_error=error)
 except Exception as error:
  report.update(status='failed',error_type=type(error).__name__)
  raise
 finally:
  (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(dict(directory=str(directory),**report)))
if __name__=='__main__':main()
