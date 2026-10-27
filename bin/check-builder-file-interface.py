"""One fixed independent wrapper check against the retained native project."""
import datetime as dt,hashlib,json,pathlib,subprocess,sys,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1];BACK=ROOT.parent/'jumpserve-back-end'
sys.path.insert(0,str(BACK/'research_workflow'))
import generated_package
IMAGE='jumpserve-netem-iperf-test@sha256:3bfc9b1b5ff3f4071334f4c0529ab5e8dc6188b13523bd9a8b4ce1259d669d01'
source=ROOT/'.test-artifacts/experiment-builder-release/20261027T193546166732Z';entry=json.loads((source/'recovered-entry.json').read_bytes())
base=ROOT/'.test-artifacts/builder-file-interface'/dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');inputs=base/'inputs';project=base/'original-project';output=base/'output'
for p in (inputs,project,output):p.mkdir(parents=True,exist_ok=False)
sha=lambda b:hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(source/'originals.zip') as z:
 for name,item in entry['files'].items():
  if not name.startswith('project/'):continue
  raw=z.read(item['archive_path']);assert sha(raw)==item['sha256'];target=project/name.removeprefix('project/');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
raw=generated_package.freeze(project);(inputs/'project.zip').write_bytes(raw);wrapper=pathlib.Path(generated_package.__file__).read_bytes();(inputs/'wrapper.py').write_bytes(wrapper)
spec=dict(version='network-execution-v1',runner='built-package-v1',configuration_identity='file-interface-software-control',replication=0,config=dict(mode='emulated',arguments=[],parameters={}),metrics=[dict(name='received_bytes',units='bytes',planned_observations=1)],limits=dict(wall_seconds=60,max_instances=1,max_output_bytes=1000000,max_network_bytes=100000000))
(inputs/'spec.json').write_text(json.dumps(spec)+'\n')
command=['docker','run','--rm','--network','none','--read-only','--memory','512m','--pids-limit','64','--cap-drop','ALL',
 '--mount','type=bind,src='+str(inputs)+',dst=/input,readonly','--mount','type=bind,src='+str(output)+',dst=/output','-w','/output',
 '-e','JUMPSERVE_SPEC=/input/spec.json','-e','JUMPSERVE_INPUTS=/input','-e','JUMPSERVE_OUTPUT=/output/output.json',IMAGE,'python3','/input/wrapper.py']
result=subprocess.run(command,capture_output=True,timeout=45);(base/'stdout.bin').write_bytes(result.stdout);(base/'stderr.bin').write_bytes(result.stderr)
report=dict(protocol='builder-file-interface-regression-v1',kind='independent implementation correctness check',source_archive_sha256=entry['source_archive']['sha256'],project_sha256=sha(raw),wrapper_sha256=sha(wrapper),image=IMAGE,exit_code=result.returncode,defect_observed=result.returncode!=0 and b'JSONDecodeError' in result.stderr,source_preserved=True,program_version='Original native project; no correction',limitations='Uses local ARM Linux image, not a fresh EC2 reproduction. Demonstrates file-path interface failure; prior 1001-byte loopback observation remains valid under its recorded development environment.',reviewer=dict(identity='Primary Codex AI implementer',type='AI',independent=False),measured_charges_usd=None)
(base/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(directory=str(base),**report),indent=2))
if not report['defect_observed']:raise SystemExit('Expected interface discrepancy was not demonstrated; investigate before attributing it.')
