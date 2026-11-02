"""Execute fixed self-install/rollback and lost-ack paths with synthetic services."""
import copy,importlib.util,io,json,os,shlex,subprocess,sys,tempfile,unittest,uuid
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('self_release',ROOT/'bin/supervisor-runtime-release.py');release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class SelfInstall(unittest.TestCase):
 def test_initial_baseline_requires_exact_source_and_reads_back_the_original_install(self):
  bootstrap_spec=importlib.util.spec_from_file_location('initial_self_baseline',ROOT/'bin/platform-supervisor.py');bootstrap=importlib.util.module_from_spec(bootstrap_spec);bootstrap_spec.loader.exec_module(bootstrap)
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'packet.json';revision='b'*40;command=str(uuid.uuid4());packet=dict(backend_revision=revision,bundle_sha256='a'*64,worker_id=release.HOST,files={'platform_supervisor/worker.py':'c'*64})
   receipt=dict(passed=True,installed_files_verified=True,bundle_sha256='a'*64,revision=revision)
   def git(args,**kwargs):
    if args[:3]==['git','status','--porcelain']:return ''
    if args[-1].endswith('/commits/main'):return json.dumps(dict(sha=revision))
    return json.dumps(dict(check_runs=[dict(name='Platform validation',conclusion='success')]))
   def aws(*args,**kwargs):
    if args[1]=='list-commands':return dict(Commands=[])
    if args[1]=='send-command':return dict(Command=dict(CommandId=command))
    if args[1]=='get-command-invocation':return dict(Status='Success',ResponseCode=0,StandardOutputContent=json.dumps(receipt))
    raise AssertionError(args)
   admin=Mock();admin.literal=lambda v:"'"+str(v).replace("'","''")+"'"
   with patch.object(bootstrap,'validate'),patch.object(bootstrap,'target'),patch.object(bootstrap.subprocess,'check_output',side_effect=git),patch.object(bootstrap,'aws',side_effect=aws) as cloud,patch.object(bootstrap,'admin',return_value=admin),patch('builtins.print'):
    bootstrap.activate_self_runtime(packet,path);admin.query.assert_not_called()
    bootstrap.activate_self_runtime(packet,path)
   self.assertTrue((Path(tmp)/'self-runtime-activation.json').is_file());self.assertEqual(sum(c.args[1]=='send-command' for c in cloud.call_args_list),1)
   self.assertFalse(admin.query.call_args.kwargs['read_only']);self.assertIn('platform_supervisor_activate',admin.query.call_args.args[0])
 def test_atomic_switch_and_start_failure_restore_the_actual_original_release(self):
  for fail in (False,True):
   with self.subTest(fail=fail),tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp).resolve();opt=root/'opt';var=root/'var';var.mkdir();old=opt/'platform-releases'/('a'*64);new=opt/'platform-releases'/('b'*64)
    old.mkdir(parents=True);new.mkdir();(old/'worker.py').write_bytes(b'original');(new/'worker.py').write_bytes(b'qualified')
    (opt/'platform').symlink_to(old,target_is_directory=True);(opt/'runtime').mkdir();(opt/'runtime/science.py').write_bytes(b'frozen scientific code')
    previous=dict(bundle_sha256='a'*64,bundle_files={'worker.py':release.sha(b'original')});files={'worker.py':release.sha(b'qualified')}
    command=release.install_script(str(uuid.uuid4()),'b'*64,files,previous)[-1];code=shlex.split(command)[-1].replace('/opt/jumpserve',str(opt)).replace('/var/lib/jumpserve-platform',str(var))
    def systemd(args,**kwargs):
     if fail and args[:2]==['systemctl','start'] and (opt/'platform').resolve()==new:raise subprocess.CalledProcessError(1,args)
     return subprocess.CompletedProcess(args,0)
    with patch.object(subprocess,'run',side_effect=systemd),patch('builtins.print'):
     if fail:
      with self.assertRaises(subprocess.CalledProcessError):exec(compile(code,'fixed-install-fixture','exec'),{})
     else:exec(compile(code,'fixed-install-fixture','exec'),{})
    self.assertEqual((opt/'platform').resolve(),old if fail else new)
    self.assertEqual((opt/'runtime/science.py').read_bytes(),b'frozen scientific code');self.assertEqual((old/'worker.py').read_bytes(),b'original')
    self.assertEqual(next(var.glob('before-self-update-*')).stat().st_mode&0o777,0o600)
 def fixture(self,tmp):
  op,command,artifact=[str(uuid.uuid4()) for _ in range(3)];revision='b'*40;workflow='c'*40
  scope=dict(previous_files={'policy.json':'d'*64},files={'policy.json':'d'*64},version=release.VERSION)
  previous=dict(source_revision='a'*40,files=scope['previous_files'],bundle_files={},bundle_sha256='a'*64)
  certificate=release.raw(dict(scope=scope,passed=True,policy_sha256='d'*64));value=b'synthetic qualified bundle';digest=release.sha(value)
  out=Path(tmp);(out/'qualified.json').write_bytes(release.raw(dict(scope=scope,bundle_files={'platform_supervisor/policy.json':'d'*64},bundle_sha256=digest)));(out/'bundle.zip').write_bytes(value)
  expected=dict(component='supervisor-runtime',revision=revision,previous_revision=previous['source_revision'],qualification_artifact_id=artifact,workflow_revision=workflow)
  operation=dict(id=op,task_id=str(uuid.uuid4()),request=expected);admissions=[]
  ssm=Mock();ssm.get_command_invocation.return_value=dict(Status='Success',ResponseCode=0,StandardOutputContent=json.dumps(dict(passed=True,bundle_sha256=digest,installed_files_verified=True)))
  ssm.get_paginator.return_value.paginate.return_value=[dict(Commands=[dict(Comment='platform-self-update-'+op,InstanceIds=[release.HOST],CommandId=command)])]
  session=Mock();sts=Mock();sts.get_caller_identity.return_value={'Account':release.ACCOUNT};secret=Mock();secret.get_secret_value.return_value={'SecretString':'synthetic-not-a-real-credential'};s3=Mock()
  session.client.side_effect=lambda name:{'ssm':ssm,'sts':sts,'secretsmanager':secret,'s3':s3}[name]
  def request(key,path,body=None):
   if path.endswith('platform_supervisor_runtime'):return previous
   if '/platform_operations?' in path:return [operation]
   if '/platform_artifacts?' in path:return [dict(storage_path='synthetic/original',sha256=release.sha(certificate))]
   if path.endswith('platform_supervisor_install'):
    if body['p_command'] is not None:return dict(recorded=True)
    admissions.append(body);return dict(dispatch_allowed=len(admissions)==1,command_id=None)
   if path.endswith('platform_supervisor_activate'):return body['p_manifest']
   raise AssertionError(path)
  def urlopen(req,**kwargs):return io.BytesIO(json.dumps(dict(sha=revision)).encode() if 'api.github.com' in req.full_url else certificate)
  env=dict(PLATFORM_OPERATION_ID=op,SUPERVISOR_REVISION=revision,PREVIOUS_SUPERVISOR_REVISION=previous['source_revision'],SUPERVISOR_QUALIFICATION_ARTIFACT=artifact,GITHUB_SHA=workflow)
  return session,ssm,request,urlopen,env,command
 def test_lost_ssm_acknowledgment_reconciles_the_same_command_without_redispatch(self):
  with tempfile.TemporaryDirectory() as tmp:
   session,ssm,request,urlopen,env,command=self.fixture(tmp);ssm.send_command.side_effect=RuntimeError('Synthetic lost acknowledgment after dispatch')
   with patch.dict(sys.modules,{'boto3':Mock(Session=Mock(return_value=session))}),patch.dict(os.environ,env),patch.object(release,'OUT',Path(tmp)),patch.object(release,'request',side_effect=request),patch.object(release.urllib.request,'urlopen',side_effect=urlopen),patch('builtins.print'):
    previous_cwd=Path.cwd()
    try:
     os.chdir(tmp)
     with self.assertRaisesRegex(RuntimeError,'lost acknowledgment'):release.execute()
     release.execute()
     proof=json.loads(Path('production-verification.json').read_bytes());self.assertEqual(proof['command_id'],command);self.assertTrue(proof['installed_files_verified'])
    finally:os.chdir(previous_cwd)
   self.assertEqual(ssm.send_command.call_count,1)
 def test_ambiguous_original_installation_never_dispatches_a_new_command(self):
  with tempfile.TemporaryDirectory() as tmp:
   session,ssm,request,urlopen,env,_=self.fixture(tmp);ssm.send_command.side_effect=RuntimeError('Lost ack');ssm.get_paginator.return_value.paginate.return_value=[dict(Commands=[])]
   with patch.dict(sys.modules,{'boto3':Mock(Session=Mock(return_value=session))}),patch.dict(os.environ,env),patch.object(release,'OUT',Path(tmp)),patch.object(release,'request',side_effect=request),patch.object(release.urllib.request,'urlopen',side_effect=urlopen):
    with self.assertRaises(RuntimeError):release.execute()
    with self.assertRaisesRegex(ValueError,'no command resent'):release.execute()
   self.assertEqual(ssm.send_command.call_count,1)
 def test_async_handoff_waits_without_dispatch_then_uses_one_original_install(self):
  with tempfile.TemporaryDirectory() as tmp:
   session,ssm,request,urlopen,env,command=self.fixture(tmp);ssm.send_command.return_value=dict(Command=dict(CommandId=command));polls=[]
   def drain(key,path,body=None):
    if path.endswith('platform_supervisor_install') and body['p_command'] is None:
     polls.append(body)
     if len(polls)<3:
      self.assertEqual(ssm.send_command.call_count,0);return dict(dispatch_allowed=False,wait_for_safe_boundary=True,command_id=None)
    return request(key,path,body)
   previous_cwd=Path.cwd()
   try:
    os.chdir(tmp)
    with patch.dict(sys.modules,{'boto3':Mock(Session=Mock(return_value=session))}),patch.dict(os.environ,env),patch.object(release,'OUT',Path(tmp)),patch.object(release,'request',side_effect=drain),patch.object(release.urllib.request,'urlopen',side_effect=urlopen),patch.object(release.time,'sleep'):
     release.execute()
   finally:os.chdir(previous_cwd)
   self.assertEqual(len(polls),3);self.assertEqual(ssm.send_command.call_count,1)
 def test_workflow_qualifies_without_credentials_and_uses_only_fixed_oidc_release_role(self):
  text=(ROOT/'.github/workflows/supervisor-runtime-release.yml').read_text()
  self.assertLess(text.index('supervisor-runtime-release.py qualify'),text.index('configure-aws-credentials'))
  self.assertIn('role-to-assume: arn:aws:iam::395567831870:role/JumpServePlatformRelease',text)
  self.assertNotIn('secrets.AWS_ACCESS_KEY_ID',text);self.assertIn('cancel-in-progress: false',text)
  commands=release.install_script(str(uuid.uuid4()),'a'*64,{},dict(bundle_sha256='b'*64,bundle_files={}))
  self.assertTrue(all(isinstance(c,str) for c in commands));self.assertNotIn('supabase-service-key','\n'.join(commands))

if __name__=='__main__':unittest.main()
