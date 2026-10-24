"""Fixed OpenClaw host diagnostics/SSM repair with a temporary caller-only SSH rule.

No command, host, account, path or key inputs are accepted. Never reads OAuth data.
"""
import argparse,datetime as dt,importlib.util,ipaddress,json,os,shlex,subprocess,time,urllib.request,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('paper_worker_guard',ROOT/'bin/openclaw-release.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['inspect','inspect-tunnel','repair-ssm','cleanup-endpoint','reboot-paused-worker']);a=p.parse_args()
 directory=ROOT/'.test-artifacts/paper-worker-repair'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True,mode=0o700)
 receipt=dict(mode=a.mode,status='running',started_at=r.stamp(),measured_charges_usd=None)
 rule=None;group=None;endpoint=None;endpoint_group=None
 def save():(directory/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
 try:
  receipt['targets']=r.target();identity=r.instance()
  if identity!='i-087f1493809643115':raise ValueError('Only the existing declared worker may be inspected')
  if a.mode=='cleanup-endpoint':
   # These exact resources belong to the retained failed private-tunnel attempt.
   endpoint='eice-02fe524bc95e0861e';endpoint_group='sg-0c686111b5ff6a4ad'
   receipt.update(temporary_endpoint=endpoint,temporary_endpoint_group=endpoint_group,status='cleanup-requested');save();return
  if a.mode=='reboot-paused-worker':
   if r.admin.query("select count(*) count from research_autonomy_tasks where status='running'")[0]['count'] or r.admin.query("select count(*) count from research_model_dispatches where status in ('queued','running','unknown')")[0]['count']:raise RuntimeError('Drain or reconcile active model work before reboot')
   if not instance_paused():raise RuntimeError('Only the paused authentication worker may be rebooted')
   receipt['before']=r.aws('ec2','describe-instance-status','--instance-ids',identity,'--include-all-instances')
   r.aws('ec2','reboot-instances','--instance-ids',identity);receipt.update(status='reboot-requested',instance_id=identity);save();return
  instance=r.aws('ec2','describe-instances','--instance-ids',identity)['Reservations'][0]['Instances'][0]
  if instance['State']['Name']!='running' or len(instance['SecurityGroups'])!=1:raise ValueError('Unexpected worker placement/state')
  group=instance['SecurityGroups'][0]['GroupId']
  if group!='sg-0b4f8e89ed3c5fc0f':raise ValueError('Unexpected worker security group')
  before=r.aws('ec2','describe-security-groups','--group-ids',group)['SecurityGroups'][0]['IpPermissions']
  if before:raise ValueError('Expected no preexisting inbound rules; do not alter unknown access')
  tunnel=a.mode in ('inspect-tunnel','repair-ssm')
  key=directory/'temporary-key'
  subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True,capture_output=True,timeout=10)
  if tunnel:
   endpoint_group=r.aws('ec2','create-security-group','--vpc-id',instance['VpcId'],'--group-name','jumpserve-paper-repair-'+directory.name.lower(),'--description','Temporary private endpoint for fixed JumpServe worker repair')['GroupId']
   receipt['temporary_endpoint_group']=endpoint_group;save()
   endpoint=r.aws('ec2','create-instance-connect-endpoint','--subnet-id',instance['SubnetId'],'--security-group-ids',endpoint_group,'--no-preserve-client-ip','--client-token',str(uuid.uuid4()))['InstanceConnectEndpoint']['InstanceConnectEndpointId']
   receipt['temporary_endpoint']=endpoint;save()
   for attempt in range(36):
    state=r.aws('ec2','describe-instance-connect-endpoints','--instance-connect-endpoint-ids',endpoint)['InstanceConnectEndpoints'][0]['State']
    if state=='create-complete':break
    if state=='create-failed':raise RuntimeError('Private repair endpoint failed to initialize')
    time.sleep(5)
   else:raise RuntimeError('Private endpoint readiness exceeded 180-second bound')
   permission=[dict(IpProtocol='tcp',FromPort=22,ToPort=22,UserIdGroupPairs=[dict(GroupId=endpoint_group,Description='Temporary private fixed-worker SSM repair')])]
  else:
   with r.prior.guard.OPEN.open('https://checkip.amazonaws.com',timeout=15) as response:address=str(ipaddress.IPv4Address(response.read(100).decode().strip()))
   permission=[dict(IpProtocol='tcp',FromPort=22,ToPort=22,IpRanges=[dict(CidrIp=address+'/32',Description='JumpServe fixed-worker temporary SSM repair')])]
  admitted=r.aws('ec2','authorize-security-group-ingress','--group-id',group,'--ip-permissions',json.dumps(permission))
  rule=admitted['SecurityGroupRules'][0]['SecurityGroupRuleId'];receipt.update(instance_id=identity,temporary_rule_id=rule,transport='private AWS endpoint' if tunnel else 'caller-only direct SSH');save()
  pushed=r.aws('ec2-instance-connect','send-ssh-public-key','--instance-id',identity,'--instance-os-user','ec2-user','--availability-zone',instance['Placement']['AvailabilityZone'],'--ssh-public-key','file://'+str(key)+'.pub')
  if pushed.get('Success') is not True:raise ValueError('Ephemeral instance key was not accepted')
  commands='''set -eu
df -h /
free -m
sudo systemctl is-active amazon-ssm-agent.service || true
sudo rpm -V amazon-ssm-agent || true
sudo ls -l /usr/bin/ssm-document-worker /usr/bin/ssm-session-worker /usr/bin/amazon-ssm-agent
sudo du -sh /var/lib/amazon/ssm /var/lib/jumpserve-openclaw /var/log
sudo tail -n 35 /var/log/amazon/ssm/errors.log
'''
  if a.mode=='repair-ssm':commands='''set -eu
sudo dnf reinstall -y amazon-ssm-agent
sudo systemctl restart amazon-ssm-agent.service
sudo systemctl is-active amazon-ssm-agent.service
sudo rpm -V amazon-ssm-agent
'''
  options=[]
  if tunnel:options=['-o','ProxyCommand='+shlex.join(['aws','ec2-instance-connect','open-tunnel','--instance-id',identity,'--instance-connect-endpoint-id',endpoint,'--remote-port','22','--profile','jumpserve','--region','us-east-1'])]
  command=['ssh','-F','/dev/null','-i',str(key),'-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(directory/'known_hosts'),'-o','ConnectTimeout=25',*options,'ec2-user@'+(instance['PrivateIpAddress'] if tunnel else instance['PublicIpAddress']),commands]
  result=subprocess.run(command,capture_output=True,timeout=180);(directory/'stdout.txt').write_bytes(result.stdout);(directory/'stderr.txt').write_bytes(result.stderr)
  receipt.update(exit_code=result.returncode,stdout=result.stdout.decode(errors='replace')[-14000:],stderr=result.stderr.decode(errors='replace')[-2000:])
  if result.returncode:raise RuntimeError('Fixed worker diagnostic/repair command failed; original output retained')
  receipt['status']='passed'
 except Exception as error:receipt.update(status='failed',reason=str(error));raise
 finally:
  try:
   if rule:
    r.aws('ec2','revoke-security-group-ingress','--group-id',group,'--security-group-rule-ids',rule)
    remaining=r.aws('ec2','describe-security-groups','--group-ids',group)['SecurityGroups'][0]['IpPermissions']
    receipt['temporary_access_removed']=not remaining
    if remaining:receipt.update(status='failed',reason='Unexpected inbound access remains after cleanup')
   if endpoint:
    values=r.aws('ec2','describe-instance-connect-endpoints','--filters','Name=instance-connect-endpoint-id,Values='+endpoint)['InstanceConnectEndpoints']
    if values and values[0]['State'] not in ('delete-complete','delete-in-progress'):
     if values[0]['State']=='create-in-progress':raise RuntimeError('Endpoint is still creating; deletion must resume after its state changes')
     r.aws('ec2','delete-instance-connect-endpoint','--instance-connect-endpoint-id',endpoint)
    for attempt in range(36):
     values=r.aws('ec2','describe-instance-connect-endpoints','--filters','Name=instance-connect-endpoint-id,Values='+endpoint)['InstanceConnectEndpoints']
     if not values or values[0]['State']=='delete-complete':break
     time.sleep(5)
    receipt['temporary_endpoint_deleted']=not values or values[0]['State']=='delete-complete'
   if endpoint_group:
    r.aws('ec2','delete-security-group','--group-id',endpoint_group);receipt['temporary_endpoint_group_deleted']=True
  except Exception as cleanup_error:receipt.update(status='cleanup-pending',cleanup_reason=str(cleanup_error)[:1000])
  finally:receipt['ended_at']=r.stamp();save();print(json.dumps(dict(directory=str(directory),**receipt),indent=2))

def instance_paused():
 with r.prior.guard.OPEN.open('https://d3o7xdethb.execute-api.us-east-1.amazonaws.com/research/capabilities',timeout=20) as response:cap=json.load(response)
 return cap['autonomy']['runtime']['status']=='auth-required'

if __name__=='__main__':main()
