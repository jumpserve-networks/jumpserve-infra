"""Fixed-target online OpenClaw storage expansion; never replaces the worker."""
import argparse,datetime as dt,importlib.util,json,pathlib,shlex
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release',ROOT/'bin/openclaw-release.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
BASE=ROOT/'.test-artifacts/openclaw-storage-v1'
CONFIG=json.loads((ROOT/'openclaw-worker-storage.json').read_bytes())
INSTANCE='i-087f1493809643115';VOLUME='vol-0993b9127ac7a8231';SIZE=300

def save(path,value):path.write_text(json.dumps(value,indent=2)+'\n');path.chmod(0o600)

def target():
    identity=r.target()
    assert CONFIG['instance_id']==INSTANCE and CONFIG['volume_id']==VOLUME and CONFIG['desired_root_volume_gib']==SIZE and r.instance()==INSTANCE
    volume=r.aws('ec2','describe-volumes','--volume-ids',VOLUME)['Volumes'][0]
    assert volume['VolumeType']=='gp3' and volume['Encrypted'] and len(volume['Attachments'])==1 and volume['Attachments'][0]['InstanceId']==INSTANCE and volume['Attachments'][0]['Device']=='/dev/xvda'
    assert volume['Size'] in (48,SIZE),'Unexpected capacity; inspect retained volume identity before changing anything.'
    return identity,volume

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['snapshot','expand','status','grow','host-status','verify']);args=parser.parse_args()
    BASE.mkdir(parents=True,exist_ok=True);out=BASE/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir()
    report=dict(protocol=CONFIG['version'],mode=args.mode,status='running',started_at=r.stamp(),measured_storage_charges_usd=None)
    try:
        report['targets'],volume=target();report['volume_gib']=volume['Size']
        if args.mode=='snapshot':
            assert not (BASE/'snapshot.json').exists(),'Snapshot already requested; reconcile the existing ID.'
            active=r.admin.query("select (select count(*) from research_autonomy_tasks where status='running')+(select count(*) from research_model_dispatches where status in ('queued','running')) count")[0]['count'];assert active==0
            item=r.aws('ec2','create-snapshot','--volume-id',VOLUME,'--description','JumpServe user-authorized 300-GiB builder expansion '+out.name,'--tag-specifications',json.dumps([dict(ResourceType='snapshot',Tags=[dict(Key='Project',Value='JumpServeOpenClaw'),dict(Key='Purpose',Value='Before300GiBStorageExpansion')])]))
            save(BASE/'snapshot.json',dict(snapshot_id=item['SnapshotId'],source_volume=VOLUME,source_size_gib=volume['Size'],requested_at=r.stamp(),consistency='Crash-consistent snapshot; provider work paused by storage guard. No credential contents read.'))
            report['snapshot_id']=item['SnapshotId']
        elif args.mode=='expand':
            backup=json.loads((BASE/'snapshot.json').read_bytes());snapshot=r.aws('ec2','describe-snapshots','--snapshot-ids',backup['snapshot_id'])['Snapshots'][0]
            assert snapshot['VolumeId']==VOLUME and snapshot['Encrypted'] and snapshot['State'] in ('pending','completed')
            report['snapshot']=dict(id=snapshot['SnapshotId'],state=snapshot['State'])
            if volume['Size']<SIZE:report['modification']=r.aws('ec2','modify-volume','--volume-id',VOLUME,'--size',str(SIZE))['VolumeModification']
            else:report['modification']='Target already requested; reconcile existing modification.'
        elif args.mode=='status':
            report['modifications']=r.aws('ec2','describe-volumes-modifications','--volume-ids',VOLUME)['VolumesModifications']
            backup=json.loads((BASE/'snapshot.json').read_bytes());snapshot=r.aws('ec2','describe-snapshots','--snapshot-ids',backup['snapshot_id'])['Snapshots'][0];report['snapshot']=dict(id=snapshot['SnapshotId'],state=snapshot['State'],progress=snapshot['Progress'])
        elif args.mode=='grow':
            assert volume['Size']==SIZE
            changes=r.aws('ec2','describe-volumes-modifications','--volume-ids',VOLUME)['VolumesModifications'];assert changes and changes[0]['TargetSize']==SIZE and changes[0]['ModificationState'] in ('optimizing','completed')
            assert not (BASE/'grow-command.json').exists(),'Inspect the original growth command before repeating it.'
            commands=['set -eu',"test \"$(lsblk -dn -o SERIAL /dev/nvme0n1 | tr -d ' -')\" = vol0993b9127ac7a8231","test \"$(findmnt -n -o SOURCE /)\" = /dev/nvme0n1p1","test \"$(findmnt -n -o FSTYPE /)\" = xfs",'df -B1 /','env TMPDIR=/run growpart /dev/nvme0n1 1','xfs_growfs -d /','df -B1 /','systemctl is-active jumpserve-openclaw.service']
            report['command']=r.ssm(commands);save(BASE/'grow-command.json',report['command'])
        elif args.mode=='host-status':
            command=json.loads((BASE/'grow-command.json').read_bytes());value=r.aws('ssm','get-command-invocation','--command-id',command['command_id'],'--instance-id',INSTANCE)
            report['command_status']=value['Status'];report['stdout']=value.get('StandardOutputContent','');report['stderr']=value.get('StandardErrorContent','');save(BASE/'grow-result.json',value)
        else:
            grown=json.loads((BASE/'grow-result.json').read_bytes());assert grown['Status']=='Success' and volume['Size']==SIZE
            health=r.admin.query("select status,configuration->>'reason' reason,updated_at from research_model_workers where id='openclaw-production-v1'")
            report.update(worker=health,volume=dict(id=VOLUME,gib=volume['Size'],encrypted=volume['Encrypted']),snapshot=json.loads((BASE/'snapshot.json').read_bytes()),instance_preserved=True,assessment_reset=False)
        report['status']='complete'
    except Exception as error:report.update(status='failed',reason=str(error));raise
    finally:report['ended_at']=r.stamp();save(out/'receipt.json',report);print(json.dumps(dict(directory=str(out),**report),indent=2))

if __name__=='__main__':main()
