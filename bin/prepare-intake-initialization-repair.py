"""Prepare a source-bound intake repair packet locally; never write to production."""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def gate():
 spec=importlib.util.spec_from_file_location('intake_initialization_gate',ROOT/'assets/platform/intake-initialization-gate.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def save_once(path,raw):
 if path.is_symlink():raise ValueError('Packet files cannot be links.')
 if path.exists():
  if path.read_bytes()!=raw:raise ValueError('A different packet already exists; preserve the original.')
 else:path.write_bytes(raw)


def prepare(previous,backend,output,assessment):
 module=gate();previous=Path(previous);backend=Path(backend);output=Path(output)
 if str(uuid.UUID(assessment))!=assessment:raise ValueError('Canonical assessment identity required.')
 manifest=json.loads((ROOT/'intake-worker-runtime.json').read_bytes())
 if output.is_symlink() or output.exists() and any(output.iterdir()):raise ValueError('An empty packet directory is required; preserve earlier receipts.')
 candidate=backend/'research_workflow';scope=module.inspect(previous/'research_workflow',candidate,manifest)
 revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip()
 if not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError('Committed repair source required.')
 for name in manifest['files']:
  committed=subprocess.check_output(['git','show',revision+':research_workflow/'+name],cwd=backend)
  if module.digest(committed)!=scope['files'][name]:raise ValueError('Repair files must match the exact committed source: '+name)
 test='research_workflow/tests/test_intake_initialization.py'
 if subprocess.check_output(['git','show',revision+':'+test],cwd=backend)!=(backend/test).read_bytes():raise ValueError('Committed fresh-intake regression required.')
 output.mkdir(parents=True,exist_ok=True)
 # These fixed tests run before any install request can be prepared. No cloud
 # or model credentials are passed into the local qualification process.
 env={k:v for k,v in os.environ.items() if not k.startswith(('AWS_','SUPABASE_','OPENAI_','GITHUB_','GH_','RESEARCH_'))}
 result=subprocess.run(['python3','-B','-m','unittest','discover','-s','research_workflow/tests','-v'],cwd=backend,env=env,capture_output=True,timeout=600)
 (output/'research-checks.log').write_bytes(result.stdout+b'\n'+result.stderr)
 counts=re.findall(rb'Ran ([0-9]+) tests',result.stderr)
 if result.returncode or not counts or b'skipped=' in result.stderr:raise ValueError('Fixed research checks failed; retain the original log.')
 if module.inspect(previous/'research_workflow',candidate,manifest)!=scope:raise ValueError('Repair source changed during qualification.')
 updated=dict(manifest,source_revision=revision,source_binding=scope['source_binding'],files=scope['files'])
 updated['qualification']='Exact initialization correction; no scientific/request/native transport changes.'
 buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
  values={name:(candidate/name).read_bytes() for name in updated['files']}
  values['intake-manifest.json']=module.canonical(updated)+b'\n'
  for name,raw in sorted(values.items()):
   info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;archive.writestr(info,raw)
 release=str(uuid.uuid5(uuid.NAMESPACE_URL,'jumpserve:'+scope['source_binding']+':'+assessment))
 packet=dict(version=module.VERSION,assessment_id=assessment,release_id=release,source_revision=revision,
  scope=scope,previous_manifest=manifest,manifest=updated,bundle_sha256=module.digest(buffer.getvalue()),
  gate_sha256=module.digest(Path(module.__file__).read_bytes()),research_checks=int(counts[-1]),
  checks_sha256=module.digest(result.stdout+b'\n'+result.stderr),production_mutations=0,
  installed=False,requires_explicit_deployment=True)
 save_once(output/'bundle.zip',buffer.getvalue())
 save_once(output/'intake-worker-runtime.json',module.canonical(updated)+b'\n')
 sql=(ROOT/'assets/platform/intake-initialization-resume.sql').read_text()
 for key,value in dict(STUDY=assessment,BINDING=scope['source_binding'],RELEASE=release,REVISION=revision).items():sql=sql.replace('@'+key+'@',value)
 save_once(output/'resume-after-verified-install.sql',sql.encode())
 # Timings in unit-test output can vary; the first retained successful packet
 # owns its original check receipt and is never silently overwritten.
 save_once(output/'packet.json',module.canonical(packet)+b'\n')
 print(json.dumps({k:packet[k] for k in ('source_revision','bundle_sha256','research_checks','production_mutations','installed')}))
 return packet


if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--previous',type=Path,required=True);parser.add_argument('--backend',type=Path,required=True)
 parser.add_argument('--output',type=Path,required=True);parser.add_argument('--assessment',required=True)
 args=parser.parse_args();prepare(args.previous,args.backend,args.output,args.assessment)
