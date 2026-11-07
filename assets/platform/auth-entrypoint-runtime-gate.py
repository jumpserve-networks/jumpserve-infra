"""Qualify only the exact Node 24 authentication CLI entrypoint correction."""
import hashlib,json,shutil
from pathlib import Path
VERSION='research-controller-recovery-v1'
PROFILE='auth-helper-entrypoint-v1'
CHECKS='auth-entrypoint-runtime-checks.py'
APPROVAL='policies/autonomous-repair-release-v1.json'
OVERLAY='auth-entrypoint-overlay-v1'
CAPTURE_TEST='tests/test_captured_provider_failures.py'
TESTS=['tests/openclaw_auth_entrypoint_test.mjs','tests/test_openclaw_auth_entrypoints.py']
PATHS=['dispatch_recovery.py','openclaw_auth.mjs',APPROVAL]
PREVIOUS_AUTH='ff5a01312d3539e091e60cf060f7433b087f390f5d126e8c8baa065ac5a11d63'
class ScopeError(ValueError):pass
def digest(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def load(path):
 path=Path(path)
 if path.is_symlink() or not path.is_file():raise ScopeError('Exact plain source required.')
 return path.read_bytes()
def correction(raw):
 if digest(raw)!=PREVIOUS_AUTH:raise ScopeError('Frozen authentication owner differs.')
 return raw.replace(b'import {fileURLToPath, pathToFileURL}',b'import {pathToFileURL}').replace(
  b'if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)) {',b'if(import.meta.main) {')
def inspect(before,after,manifest):
 before,after=Path(before),Path(after);files={};changed=[]
 if not isinstance(manifest.get('files'),dict) or not manifest['files']:raise ScopeError('Bound predecessor required.')
 for name,h in manifest['files'].items():
  old,new=load(before/name),load(after/name)
  if digest(old)!=h:raise ScopeError('Predecessor source differs: '+name)
  files[name]=digest(new)
  if name==APPROVAL or old==new:continue
  if name!='openclaw_auth.mjs' or new!=correction(old):raise ScopeError('Only the exact CLI entrypoint correction is permitted.')
  changed.append(name)
 if changed!=['openclaw_auth.mjs']:raise ScopeError('One exact auth entrypoint correction required.')
 for p in (before/'tests').rglob('*'):
  if p.is_file() and (p.is_symlink() or load(p)!=load(after/'tests'/p.relative_to(before/'tests'))):raise ScopeError('Existing checks changed.')
 old_names={p.name for p in before.iterdir() if p.is_file() and p.suffix in ('.py','.mjs')}
 if {p.name for p in after.iterdir() if p.is_file() and p.suffix in ('.py','.mjs')}-old_names:raise ScopeError('New executable runtime module is outside this profile.')
 previous=digest(encoded({n:h for n,h in manifest['files'].items() if n!=APPROVAL}));approval=json.loads(load(before/APPROVAL))
 if approval.get('approved_for_lab_recovery') is not True or approval.get('qualified_files_sha256')!=previous:raise ScopeError('Inherited qualification differs.')
 return dict(version=VERSION,qualification_profile=PROFILE,changed_files=changed,files=files,
  source_binding=digest(encoded({n:h for n,h in files.items() if n!=APPROVAL})),previous_source_revision=manifest['source_revision'],previous_source_binding=previous,
  inherited_model_evidence_sha256=approval['evidence_sha256'],scientific_and_request_content_unchanged=True,existing_tests_unchanged=True,new_provider_calls=0)
def approval(scope,certificate_sha256):
 if scope.get('qualification_profile')!=PROFILE or scope.get('scientific_and_request_content_unchanged') is not True or len(certificate_sha256)!=64:raise ScopeError('Exact auth qualification required.')
 return dict(version='autonomous-repair-release-v1',approved_for_lab_recovery=True,qualified_files_sha256=scope['source_binding'],evidence_sha256=certificate_sha256)
def pin(previous,revision,files):
 if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision) or set(files)!=set(previous['files']):raise ScopeError('Exact source and file coverage required.')
 return dict(version=previous['version']+1,source_revision=revision,files=dict(sorted(files.items())))
def overlay(previous):
 inherited=previous.get('source_overlay')
 if not inherited or inherited.get('version')!='captured-provider-overlay-v1' or inherited.get('paths')!=['dispatch_recovery.py',APPROVAL] or inherited.get('tests')!=[CAPTURE_TEST]:raise ScopeError('Exact installed captured-recovery composition required.')
 revision=inherited['base_revision']
 if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):raise ScopeError('Exact base revision required.')
 return dict(version=OVERLAY,base_revision=revision,paths=PATHS,tests=[CAPTURE_TEST,*TESTS])
def compose(base,proposal,target,include_test=True):
 base,proposal,target=Path(base),Path(proposal),Path(target)
 if target.exists():raise ScopeError('Composition cannot overwrite an existing tree.')
 target.mkdir(parents=True)
 shutil.copytree(base/'research_workflow',target/'research_workflow',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 for name in [*PATHS,*([CAPTURE_TEST,*TESTS] if include_test else [])]:
  origin=proposal/'research_workflow'/name
  # The qualified predecessor predates these new regressions. The independent
  # candidate checks below require them, so absence cannot pass qualification.
  if name in TESTS and not origin.exists():continue
  destination=target/'research_workflow'/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(load(origin))
 return target
