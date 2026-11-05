"""Publisher request preparation cannot copy a refresh grant or replace old workers."""
import io,json,runpy,unittest
from pathlib import Path
from botocore.exceptions import ClientError

ROOT=Path(__file__).resolve().parents[1];module=runpy.run_path(str(ROOT/'bin/prepare-intake-publisher.py'))
cloud=runpy.run_path(str(ROOT/'bin/deploy-intake-publisher.py'))

class IntentStore:
 def __init__(self):self.values={}
 def put_object(self,**value):
  key=value['Key']
  if value.get('IfNoneMatch')=='*' and key in self.values:raise ClientError({'Error':{'Code':'PreconditionFailed'}},'PutObject')
  self.values[key]=value['Body']
 def get_object(self,**value):return {'Body':io.BytesIO(self.values[value['Key']])}

class Commands:
 def __init__(self,lost=False,unconfirmed=False):self.commands=[];self.sent=0;self.lost=lost;self.unconfirmed=unconfirmed
 def list_commands(self,**value):return {'Commands':self.commands}
 def send_command(self,**value):
  self.sent+=1
  command=dict(value,CommandId='10000000-0000-4000-8000-000000000001')
  if not self.unconfirmed:self.commands.append(command)
  if self.lost or self.unconfirmed:raise TimeoutError('Explicit synthetic lost acknowledgement')
  return {'Command':command}

class IntakeRelease(unittest.TestCase):
 def request(self):return cloud['request_for']('20000000-0000-4000-8000-000000000001','a'*64+'.zip','b'*64+'.service')
 def outputs(self):
  binding=json.loads((ROOT/'intake-worker-runtime.json').read_bytes())['source_binding']
  return {'JumpServeIntakeStack':dict(IntakeSourceBinding=binding,IntakeRuntimeBucket='cdk-hnb659fds-assets-395567831870-us-east-1',IntakePublisherBucket='cdk-hnb659fds-assets-395567831870-us-east-1',IntakeRuntimeObject='a'*64+'.zip',IntakePublisherObject='b'*64+'.service')}
 def test_only_adds_a_publisher_to_the_exact_existing_owner(self):
  value=module['build'](self.outputs());commands='\n'.join(value['Parameters']['commands'])
  self.assertEqual(value['InstanceIds'],['i-087f1493809643115']);self.assertIn('sha256sum --check',commands)
  self.assertIn('m["source_revision"]',commands);self.assertIn('m["source_binding"]',commands)
  self.assertIn('systemctl enable --now jumpserve-intake-access.service',commands)
  for excluded in ('restart jumpserve-openclaw','stop jumpserve-openclaw','refresh_token','get-parameter','get-secret-value'):
   self.assertNotIn(excluded,commands)
 def test_wrong_source_account_or_mutable_asset_is_refused_before_a_request_exists(self):
  for key,value in (('IntakeSourceBinding','f'*64),('IntakeRuntimeBucket','another-account'),('IntakePublisherObject','latest.service'),('IntakeRuntimeObject','a'*64+';whoami')):
   outputs=self.outputs();outputs['JumpServeIntakeStack'][key]=value
   with self.assertRaises(ValueError):module['build'](outputs)
 def test_cloud_release_reuses_the_original_command(self):
  storage=IntentStore();commands=Commands();request=self.request();run=cloud['dispatch_once'];release='20000000-0000-4000-8000-000000000001'
  first=run(storage,commands,release,request);self.assertEqual(run(storage,commands,release,request),first);self.assertEqual(commands.sent,1)
  changed=dict(request,Comment='Different intent')
  with self.assertRaises(ValueError):run(storage,commands,release,changed)
  self.assertEqual(commands.sent,1)
 def test_lost_send_acknowledgement_reconciles_without_another_send(self):
  storage=IntentStore();commands=Commands(lost=True);request=self.request();run=cloud['dispatch_once'];release='20000000-0000-4000-8000-000000000001'
  with self.assertRaises(TimeoutError):run(storage,commands,release,request)
  self.assertEqual(run(storage,commands,release,request),commands.commands[0]['CommandId']);self.assertEqual(commands.sent,1)
 def test_unconfirmed_original_never_replays(self):
  storage=IntentStore();commands=Commands(unconfirmed=True);request=self.request();run=cloud['dispatch_once'];release='20000000-0000-4000-8000-000000000001'
  with self.assertRaises(TimeoutError):run(storage,commands,release,request)
  with self.assertRaisesRegex(ValueError,'unconfirmed'):run(storage,commands,release,request)
  self.assertEqual(commands.sent,1)

if __name__=='__main__':unittest.main()
