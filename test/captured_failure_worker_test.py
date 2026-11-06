"""Worker install executes once; uncertain command acknowledgments cannot replay."""
import hashlib,importlib.util,io,json,shlex,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('worker_broker',ROOT/'bin/captured-failure-worker-release.py');broker=importlib.util.module_from_spec(s);s.loader.exec_module(broker)
class WorkerInstall(unittest.TestCase):
 def environment(self,lost=False):
  op='11111111-1111-4111-8111-111111111111';cmd='22222222-2222-4222-8222-222222222222';revision='a'*40;objects={};commands=[];admitted=False;receipt=None;activated=[]
  db=Mock();s3=Mock();ssm=Mock();session=Mock();session.client.side_effect=lambda name:ssm if name=='ssm' else s3
  def request(path,payload):
   nonlocal admitted,receipt
   if path.endswith('_activate'):activated.append(payload);return payload['p_verification']
   if payload['p_command'] is not None:receipt=payload['p_command'];return dict(command_id=receipt,dispatch_allowed=False)
   if admitted:return dict(dispatch_allowed=False,command_id=receipt)
   admitted=True;return dict(dispatch_allowed=True,command_id=None)
  db.request.side_effect=request
  def put(**kw):
   if kw['Key'] in objects:raise ValueError('Immutable object exists')
   objects[kw['Key']]=kw['Body']
  s3.put_object.side_effect=put;s3.get_object.side_effect=lambda **kw:dict(Body=io.BytesIO(objects[kw['Key']]))
  def send(**kw):
   c=dict(kw,CommandId=cmd);commands.append(c)
   if lost:raise TimeoutError('Synthetic lost command acknowledgment')
   return {'Command':c}
  ssm.send_command.side_effect=send;ssm.list_commands.side_effect=lambda **kw:dict(Commands=commands)
  bundle=b'synthetic qualified bundle';h=hashlib.sha256(bundle).hexdigest()
  proof=dict(passed=True,bundle_sha256=h,installed_files_verified=True,spool_unchanged=True,credentials_unchanged=True,provider_calls=0,scientific_completion=False)
  ssm.get_command_invocation.return_value=dict(Status='Success',ResponseCode=0,StandardOutputContent=json.dumps(proof))
  q=dict(manifest=dict(source_revision=revision,files={'dispatch_recovery.py':'b'*64}),previous_manifest=dict(files={'dispatch_recovery.py':'c'*64}),scope=dict(source_binding='d'*64))
  return session,db,ssm,commands,op,revision,q,bundle,activated
 def test_lost_ack_is_reconciled_against_the_one_exact_original_command(self):
  session,db,ssm,commands,op,revision,q,bundle,activated=self.environment(True)
  with patch.object(broker,'persistence',return_value=db):
   with self.assertRaises(TimeoutError):broker.install(session,op,revision,q,bundle)
   proof=broker.install(session,op,revision,q,bundle)
  self.assertEqual(ssm.send_command.call_count,1);self.assertEqual(len(activated),1);self.assertEqual(proof['command_id'],commands[0]['CommandId'])
  self.assertEqual(commands[0]['InstanceIds'],[broker.HOST]);self.assertEqual(proof['revision'],revision)
 def test_missing_or_different_original_commands_cannot_trigger_replacement(self):
  for defect in ('missing','different'):
   with self.subTest(defect=defect):
    session,db,ssm,commands,op,revision,q,bundle,activated=self.environment(True)
    with patch.object(broker,'persistence',return_value=db):
     with self.assertRaises(TimeoutError):broker.install(session,op,revision,q,bundle)
     if defect=='missing':commands.clear()
     else:commands[0]['Parameters']={'commands':['different source']}
     with self.assertRaises(ValueError):broker.install(session,op,revision,q,bundle)
    self.assertEqual(ssm.send_command.call_count,1);self.assertEqual(activated,[])
 def test_fixed_installer_verifies_before_switch_and_preserves_state_before_restart(self):
  commands=broker.script('11111111-1111-4111-8111-111111111111','a'*64,{'dispatch_recovery.py':'b'*64},{'dispatch_recovery.py':'c'*64})
  source=shlex.split(commands[-1])[-1];compile(source,'frozen-worker-installer','exec')
  self.assertLess(source.index('for n,h in PREVIOUS.items()'),source.index("systemctl','stop"))
  self.assertLess(source.index('snapshot(state)==before'),source.index("systemctl','start"))
  self.assertIn('backup.rename(runtime)',source);self.assertIn('cwd',source)
  self.assertNotIn('get-secret-value',source);self.assertNotIn('credential(',source);self.assertNotIn('unlink(missing_ok=True)',source)
if __name__=='__main__':unittest.main()
