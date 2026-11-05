"""Fixed service release profiles cannot become arbitrary commands or SQL."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import io
from types import SimpleNamespace
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('service_release',ROOT/'bin/platform-service-release.py');service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)


class ServiceRelease(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.id='11111111-1111-4111-8111-111111111111'
  self.manifest=dict(version='platform-service-manifest-v1',request_id=self.id,profile='assessment-evidence-v1')

 def test_qualification_reads_actual_plain_manifests_without_credentials(self):
  directory=self.root/'services';directory.mkdir();(directory/(self.id+'.json')).write_text(json.dumps(self.manifest))
  self.assertEqual(service.qualify(self.root),dict(passed=True,manifests=1,credentials_used=False,provider_calls=0))
  for value in (dict(self.manifest,sql='select service_key'),dict(self.manifest,profile='arbitrary-cloud-command'),dict(self.manifest,request_id='22222222-2222-4222-8222-222222222222')):
   (directory/(self.id+'.json')).write_text(json.dumps(value))
   with self.assertRaises(ValueError):service.qualify(self.root)

 def test_manifest_links_and_oversized_files_are_rejected(self):
  directory=self.root/'services';directory.mkdir();target=self.root/'retained.json';target.write_text(json.dumps(self.manifest));path=directory/(self.id+'.json');path.symlink_to(target)
  with self.assertRaises(ValueError):service.qualify(self.root)
  path.unlink();path.write_text(' '*16001)
  with self.assertRaises(ValueError):service.qualify(self.root)

 def test_unknown_failure_or_partial_context_stops_before_any_parser_or_storage_write(self):
  evidence=dict(assessment_id=self.id,task=dict(stage='intake',status='blocked',attempts=0,context={'last_turn_id':'retained'}),review=dict(status='failed',confirmed=False,candidate_count=0))
  db=Mock();session=Mock()
  with self.assertRaises(ValueError):service.recover(db,session,dict(evidence=evidence),'operation','revision',self.root)
  db.request.assert_not_called();session.client.assert_not_called()

 def test_original_hash_and_assessment_path_are_checked_before_parse(self):
  db=service.Database('synthetic-private-key');db.request=Mock(return_value=b'original')
  artifact=dict(storage_path=self.id+'/'+'a'*64,sha256='a'*64,byte_count=8)
  with self.assertRaises(ValueError):db.original(self.id,artifact)
  artifact['storage_path']='another-assessment/'+artifact['sha256']
  with self.assertRaises(ValueError):db.original(self.id,artifact)
  self.assertEqual(db.request.call_count,1)

 def test_read_only_service_executes_evidence_reads_then_commits_exact_source(self):
  directory=self.root/'services';directory.mkdir();path=directory/(self.id+'.json');path.write_text(json.dumps(self.manifest))
  context=dict(request_id=self.id,profile='assessment-evidence-v1',manifest_path='services/'+self.id+'.json',evidence=dict(task={'id':self.id},schema={'research_artifacts':['id','sha256']},artifacts=[]))
  db=Mock();db.release.side_effect=[context,dict(verified=True)];session=Mock()
  session.client.return_value.get_secret_value.return_value={'SecretString':'synthetic-key'}
  with patch.object(service,'Database',return_value=db):self.assertEqual(service.execute(session,self.root,'operation','a'*40),{'verified':True})
  result=db.release.call_args.args[3];self.assertTrue(result['task_bound_evidence_verified']);self.assertFalse(result['scientific_completion']);self.assertEqual(result['provider_calls'],0)

 def test_original_verified_result_reconciles_without_another_service_action(self):
  db=Mock();db.release.return_value=dict(verified=True,verification={'passed':True});session=Mock();session.client.return_value.get_secret_value.return_value={'SecretString':'synthetic-key'}
  with patch.object(service,'Database',return_value=db),patch.object(service,'recover') as recover:
   result=service.execute(session,self.root,'original-operation','a'*40)
  self.assertTrue(result['verified']);recover.assert_not_called();db.release.assert_called_once()

 def environment(self,lost=False):
  objects={};commands=[];ssm=Mock();s3=Mock()
  def put(**value):
   if value['Key'] in objects:raise ValueError('Synthetic immutable-object precondition')
   objects[value['Key']]=value['Body']
  s3.put_object.side_effect=put;s3.get_object.side_effect=lambda **value:dict(Body=io.BytesIO(objects[value['Key']]))
  ssm.list_commands.side_effect=lambda **value:dict(Commands=commands)
  def send(**request):
   command=dict(request,CommandId='77777777-7777-4777-8777-777777777777');commands.append(command)
   if lost:raise TimeoutError('Synthetic lost acknowledgment')
   return {'Command':command}
  ssm.send_command.side_effect=send;ssm.get_command_invocation.return_value=dict(Status='Success',ResponseCode=0,StandardOutputContent=json.dumps(dict(passed=True,actual_parser_subprocess=True)))
  session=Mock();session.client.side_effect=lambda name:ssm if name=='ssm' else s3
  return session,ssm,commands,objects

 def test_actual_host_check_has_one_durable_command_and_reconciles_a_lost_ack(self):
  session,ssm,commands,objects=self.environment(lost=True)
  with self.assertRaises(TimeoutError):service.verify_intake_environment(session,self.id)
  proof=service.verify_intake_environment(session,self.id)
  self.assertTrue(proof['intake_environment_verified']);self.assertEqual(ssm.send_command.call_count,1)
  command=commands[0];self.assertEqual(command['InstanceIds'],['i-00dc52abbcf706670'])
  self.assertIn('runuser',command['Parameters']['commands'][1]);self.assertIn('intake-pdf-check.py',command['Parameters']['commands'][1])
  self.assertNotIn('get-secret-value',command['Parameters']['commands'][1])

 def test_unknown_command_ack_or_different_parameters_cannot_start_a_replacement(self):
  session,ssm,commands,objects=self.environment();service.verify_intake_environment(session,self.id)
  commands.clear()
  with self.assertRaises(ValueError):service.verify_intake_environment(session,self.id)
  self.assertEqual(ssm.send_command.call_count,1)


if __name__=='__main__':unittest.main()
