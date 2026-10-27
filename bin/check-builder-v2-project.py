"""Two fixed independent wrapper executions of the retained v2 TCP project."""
import datetime as dt,hashlib,json,pathlib,subprocess,sys,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
sys.path.insert(0,str(BACK/'research_workflow'))
import generated_package,network_spec
source=ROOT/'.test-artifacts/builder-qualification-v2/20261027T220810693438Z'
protocol=json.loads((ROOT/'docs/experiment-builder-portability-check-v2.json').read_bytes())
raw_archive=(source/'originals.zip').read_bytes();sha=lambda b:hashlib.sha256(b).hexdigest()
assert sha(raw_archive)==protocol['source_archive_sha256']
case=next(c for c in json.loads((source/'host-report.json').read_bytes())['cases'] if c['name']=='new-implementation')
prefix='builder-workspaces/'+pathlib.Path(case['work']).parent.name+'/workspace/'
out=ROOT/'.test-artifacts/builder-v2-portability'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
project=out/'original-project';project.mkdir()
with zipfile.ZipFile(source/'originals.zip') as z:
    original_spec=z.read(prefix+'check-spec.json')
    for name in z.namelist():
        if not name.startswith(prefix+'project/'):continue
        relative=pathlib.PurePosixPath(name.removeprefix(prefix+'project/'));assert not relative.is_absolute() and '..' not in relative.parts
        target=project/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
frozen=generated_package.freeze(project);wrapper=pathlib.Path(generated_package.__file__).read_bytes()
image=json.loads((BACK/'.test-artifacts/builder-image/selected.json').read_bytes())['image']
digest=sha(bytes(range(251))*3+bytes(range(248)));assert digest=='d57f2a1c8961773c8653c0fc54fb91c8f71c62e5f0a61d7c3c8169f5c42ecd52'
spec=dict(version='network-execution-v1',runner='built-package-v1',configuration_identity='independent-file-path-control',replication=0,config=dict(mode='emulated',arguments=[],parameters={}),metrics=[dict(name='received_bytes',units='bytes',planned_observations=1)],limits=dict(wall_seconds=30,max_instances=1,max_output_bytes=3000000,max_network_bytes=1000000))
report=dict(protocol=protocol['version'],source_archive_sha256=sha(raw_archive),project_sha256=sha(frozen),wrapper_sha256=sha(wrapper),image=image,status='failed',checks=[],live_provider_calls=0,new_cloud_instances=0,measured_charges_usd=None,limitations=protocol['limits'])
try:
    for identity,spec_bytes in [('retained-development-spec',original_spec),('canonical-server-spec',json.dumps(spec).encode())]:
        root=out/identity;inputs=root/'inputs';output=root/'output';inputs.mkdir(parents=True);output.mkdir()
        (inputs/'project.zip').write_bytes(frozen);(inputs/'wrapper.py').write_bytes(wrapper);(inputs/'spec.json').write_bytes(spec_bytes)
        command=['docker','run','--rm','--network','none','--read-only','--cpus','1','--memory','512m','--pids-limit','64','--cap-drop','ALL',
                 '--mount','type=bind,src='+str(inputs)+',dst=/input,readonly','--mount','type=bind,src='+str(output)+',dst=/output','-w','/output',
                 '-e','JUMPSERVE_SPEC=/input/spec.json','-e','JUMPSERVE_INPUTS=/input','-e','JUMPSERVE_OUTPUT=/output/output.json',image,'python3','/input/wrapper.py']
        result=subprocess.run(command,capture_output=True,timeout=45);(root/'stdout.bin').write_bytes(result.stdout);(root/'stderr.bin').write_bytes(result.stderr)
        row=dict(identity=identity,exit_code=result.returncode,spec_sha256=sha(spec_bytes));report['checks'].append(row)
        assert result.returncode==0,result.stderr.decode(errors='replace')
        original=(output/'output.json').read_bytes();parsed=network_spec.observations(original,spec['metrics'],1);observation=parsed['observations'][0]
        assert len(parsed['observations'])==1 and observation['value']==1001 and observation['units']=='bytes' and observation['status']=='recorded'
        metadata=observation['metadata'];assert metadata['received_sha256']==metadata['expected_sha256']==digest and metadata['exact_bytes_match'] and metadata['eof_observed']
        chunks=metadata['recv_chunk_sizes_bytes'];assert sum(chunks)==1001 and all(1<=n<=37 for n in chunks)
        row.update(status='passed',value=1001,units='bytes',output_sha256=sha(original),payload_sha256=digest,receive_calls=len(chunks))
    report['status']='passed'
finally:
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(directory=str(out),**report),indent=2))
