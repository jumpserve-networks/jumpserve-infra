"""Trusted deterministic eligibility gate for operational controller releases.

Scientific methods, model request construction, executors, prompts, policies,
dependencies and existing research tests cannot change through this adapter.
Candidate code is never imported by the credentialed gate.
"""
import ast,copy,hashlib,json
from pathlib import Path
VERSION='research-controller-recovery-v1'
APPROVAL='policies/autonomous-repair-release-v1.json'
FUNCTIONS={
 'autonomy.py':{'handler'},
 'autonomous_repair.py':{'diagnose','discover'},
 'autonomy_model.py':{'inspection_identifier'},
 'dispatch_recovery.py':{'ledger','confirmed','reconcile_spool','_reconcile_dispatches'},
}
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
class ScopeError(ValueError):pass
def load(path):
 path=Path(path)
 if path.is_symlink() or not path.is_file():raise ScopeError('Plain declared source required: '+str(path))
 return path.read_bytes()
class InspectionBoundary(ast.NodeTransformer):
 def visit_Expr(self,node):
  expected=ast.parse('inspection_identifier(read)').body[0]
  if ast.dump(node,include_attributes=False)==ast.dump(expected,include_attributes=False):return None
  return self.generic_visit(node)
def protected_tree(raw,name):
 tree=ast.parse(raw)
 for node in tree.body:
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in FUNCTIONS.get(name,set()):node.body=[ast.Pass()]
  elif name=='autonomy_model.py' and isinstance(node,ast.FunctionDef) and node.name=='parse':InspectionBoundary().visit(node)
  elif name=='autonomy_model.py' and isinstance(node,ast.ImportFrom) and node.module=='workflow':node.names=[n for n in node.names if n.name!='identifier']
 # The generated observation RPC is the sole permitted store routing addition.
 if name=='store.py':
  allowed=ast.parse("if name=='research_autonomy_runtime_observe':return request('/rest/v1/rpc/'+name,'POST',payload)").body[0]
  for node in tree.body:
   if isinstance(node,ast.FunctionDef) and node.name=='rpc':node.body=[n for n in node.body if ast.dump(n,include_attributes=False)!=ast.dump(allowed,include_attributes=False)]
 # An operational helper may be added without changing any other module node.
 tree.body=[n for n in tree.body if not (name=='autonomy_model.py' and isinstance(n,ast.FunctionDef) and n.name=='inspection_identifier')]
 return ast.dump(tree,include_attributes=False)
def inspect(before,after,manifest):
 before=Path(before);after=Path(after);files={};changed=[]
 if not isinstance(manifest.get('files'),dict) or not manifest['files']:raise ScopeError('Bound source manifest required.')
 for name,expected in manifest['files'].items():
  old=load(before/name);new=load(after/name)
  if digest(old)!=expected:raise ScopeError('Previous source binding differs: '+name)
  files[name]=digest(new)
  if name==APPROVAL:continue
  if old==new:continue
  if name not in set(FUNCTIONS)|{'store.py'}:raise ScopeError('Dedicated scientific or transport qualification required: '+name)
  if protected_tree(old,name)!=protected_tree(new,name):raise ScopeError('Frozen scientific/request/module content changed: '+name)
  changed.append(name)
 if not changed:raise ScopeError('No operational runtime source change requires release.')
 for path in before.parent.joinpath('research_workflow/tests').rglob('*'):
  if path.is_file() and not path.is_symlink() and path.suffix=='.py':
   relative=path.relative_to(before.parent)
   if load(path)!=load(after.parent/relative):raise ScopeError('Existing research validation changed: '+str(relative))
 existing={p.name for p in before.iterdir() if p.is_file() and p.suffix in ('.py','.mjs')}
 added={p.name for p in after.iterdir() if p.is_file() and p.suffix in ('.py','.mjs')}-existing
 if added:raise ScopeError('Additional executable modules need a declared qualification: '+','.join(sorted(added)))
 inherited=json.loads(load(before/APPROVAL))
 previous_binding=digest(canonical({n:v for n,v in manifest['files'].items() if n!=APPROVAL}))
 if not inherited.get('approved_for_lab_recovery') or inherited.get('qualified_files_sha256')!=previous_binding:raise ScopeError('Previous model/runtime qualification does not bind its source.')
 return dict(version=VERSION,changed_files=sorted(changed),files=files,
  source_binding=digest(canonical({n:v for n,v in files.items() if n!=APPROVAL})),
  previous_source_revision=manifest['source_revision'],previous_source_binding=previous_binding,
  inherited_model_evidence_sha256=inherited['evidence_sha256'],scientific_and_request_content_unchanged=True,
  existing_tests_unchanged=True,new_provider_calls=0)
def approval(scope,certificate_sha256):
 if scope.get('version')!=VERSION or scope.get('scientific_and_request_content_unchanged') is not True or scope.get('existing_tests_unchanged') is not True:raise ScopeError('Qualified operational scope required.')
 if len(certificate_sha256)!=64 or any(c not in '0123456789abcdef' for c in certificate_sha256):raise ScopeError('Immutable qualification artifact hash required.')
 return dict(version='autonomous-repair-release-v1',approved_for_lab_recovery=True,qualified_files_sha256=scope['source_binding'],evidence_sha256=certificate_sha256)
def pin(previous,revision,files):
 if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision) or set(files)!=set(previous['files']):raise ScopeError('Exact reviewed runtime source and unchanged file coverage required.')
 return dict(version=previous['version']+1,source_revision=revision,files=dict(sorted(files.items())))
