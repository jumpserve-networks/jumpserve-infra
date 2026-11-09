"""Fixed synthetic native-tool control under production systemd restrictions.

No provider inference, Google identity, experiment VM or publication is used.
The actual production source, package and image are read; only this control's
private working directory and temporary Docker resources are written.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/opt/jumpserve/runtime')
import experiment_builder as builder
import openclaw_runtime as runtime
import store
from workflow import canonical,digest

expected=json.loads((ROOT/'expected.json').read_bytes())
assert {n:digest((Path('/opt/jumpserve/runtime')/n).read_bytes()) for n in expected['files']}==expected['files']
assert builder.enabled()
image=os.environ['OPENCLAW_BUILDER_IMAGE'];assert image==expected['image']
package=builder.builder_package();assert str(package)==os.environ['OPENCLAW_BUILDER_PACKAGE']
assert os.getuid()==993 and os.getgid()==993
patch=json.loads(builder.PATCH_PATH.read_bytes())
upstream=runtime.PACKAGE/patch['path']
assert digest(upstream.read_bytes())==patch['original_sha256']
for name,sha in expected['test_files'].items():assert digest((ROOT/name).read_bytes())==sha
if not (ROOT/'report.json').exists():
    (ROOT/'.test-artifacts/builder-image').mkdir(parents=True)
    (ROOT/'.test-artifacts/builder-image/selected.json').write_bytes(canonical(dict(image=image)))
    modules=ROOT/'experiments/openclaw_pilot/runtime/node_modules';modules.mkdir(parents=True)
    (modules/'openclaw').symlink_to(runtime.PACKAGE,target_is_directory=True)
    (modules/'node').symlink_to(runtime.NODE.parents[1],target_is_directory=True)
    sys.path.insert(0,str(ROOT/'research_workflow/tests'))
    spec=importlib.util.spec_from_file_location('production_native_smoke',ROOT/'research_workflow/tests/check_experiment_builder_linux.py')
    smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)
    # Use the installed release vendor copy, rather than silently preparing another.
    smoke.prepare=lambda *_:package
    smoke.main()
    reports=list((ROOT/'.test-artifacts/experiment-builder').glob('*/report.json'));assert len(reports)==1
    native=json.loads(reports[0].read_bytes());assert native['status']=='passed' and native['provider_calls']==0
    report=dict(protocol='experiment-builder-production-v2',status='passed',kind='synthetic-provider-production-native-control',
        live_provider_calls=0,new_experiment_instances=0,image=image,uid=os.getuid(),gid=os.getgid(),
        source_files_verified=len(expected['files']),upstream_sha256=patch['original_sha256'],builder_vendor_sha256=patch['corrected_sha256'],
        production_vendor_used=True,native_control=native,measured_charges_usd=None,
        limitations=['Synthetic provider/admission/storage transport inside the native smoke, not an authenticated Google request or production SQL admission.',
                     'Real native tools/Docker execute under matching production NoNewPrivileges/PrivateTmp/ProtectHome/ProtectSystem/ReadWritePaths/MemoryMax restrictions.'])
    (ROOT/'report.json').write_bytes(canonical(report))
else:
    report=json.loads((ROOT/'report.json').read_bytes())
    assert report['status']=='passed' and report['live_provider_calls']==0,'Recover evidence only for a known completed control.'
files={}
excluded=[]
for p in ROOT.rglob('*'):
    if not p.is_file() or p.is_symlink():continue
    relative=p.relative_to(ROOT)
    selected=str(relative) in ('check.py','recover.py','expected.json','report.json','original-archive-failure.json') or str(relative).startswith('research_workflow/tests/') or '-retained-' in p.name or p.name in ('report.json','receipt.json','stdout.bin','stderr.bin','logical.json','task.txt','workspace-normalization.json') or p.name.startswith(('call-','native-request-'))
    if 'state' in relative.parts or p.name=='config.json' or 'experiments' in relative.parts or not selected:
        excluded.append(dict(path=str(relative),bytes=p.stat().st_size,reason='Outside the fixed control-evidence allowlist; configuration/state/cache/vendor content excluded.'));continue
    raw=p.read_bytes();assert len(raw)<5000000;files[str(relative)]=raw
files['archive-scope.json']=canonical(dict(excluded=excluded,selection='Exact fixed control inputs, retained synthetic requests/responses, tool outputs and receipts; no auth/config/runtime cache trees.',reexecuted_native_control=False if (ROOT/'original-archive-failure.json').exists() else None))
buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
    for name,raw in sorted(files.items()):z.writestr(name,raw)
    z.writestr('artifact-manifest.json',canonical([dict(path=n,sha256=digest(raw),bytes=len(raw)) for n,raw in sorted(files.items())]))
raw=buffer.getvalue();assert len(raw)<=20000000
path='release-verification/experiment-builder-v2/'+ROOT.name+'/native-control/'+digest(raw)+'.zip'
url='/storage/v1/object/research-workflow-raw/'+path
store.request(url,'POST',raw);assert store.request(url,raw=True)==raw
print(json.dumps(dict(status='passed',archive=dict(bucket='research-workflow-raw',path=path,sha256=digest(raw),retrieved_sha256=digest(raw),bytes=len(raw),public=False))))
