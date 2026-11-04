"""Frozen broker for operational supervisor updates, never candidate authority."""
import ast,hashlib,json,re
from pathlib import Path

VERSION='platform-supervisor-self-repair-v1'
KERNEL={'__init__.py','common.py','credentials.py','store.py','github.py','source.py','releases.py','self_runtime.py','standing_authority.py','capabilities.py','policy.json'}
METHODS={'worker.py':{'Controller.boundary','Controller.operation','Controller.coding_available','Controller.reconcile_pending','Controller.run','main'},
 'native.py':{'execute','containers','container_prefix','failure_status','reconcile'},'checks.py':{'execute'},
 'call_recovery.py':{'http_failure','effective_status','reconcile_http'}}
def digest(raw):return hashlib.sha256(raw).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def files(root):
 root=Path(root);result={}
 for p in sorted(root.glob('*')):
  if p.is_symlink():raise ValueError('Supervisor source cannot contain links')
  if p.is_file() and p.suffix in ('.py','.json'):
   if not re.fullmatch(r'[a-z_][a-z0-9_]*\.(py|json)',p.name):raise ValueError('Supervisor modules require plain Python identifiers')
   result[p.name]=digest(p.read_bytes())
 return result
def definitions(raw):
 tree=ast.parse(raw);result={}
 for node in tree.body:
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):result[node.name]=ast.dump(node,include_attributes=False)
  elif isinstance(node,ast.ClassDef):
   for fn in node.body:
    if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):result[node.name+'.'+fn.name]=ast.dump(fn,include_attributes=False)
 return result
def declarations(raw):
 # Additional functionality is declared, never executed at module import.
 for n in ast.parse(raw).body:
  if isinstance(n,(ast.Import,ast.ImportFrom)):continue
  if isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant):continue
  if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
   if header_effects(n):raise ValueError('New import-time execution is not qualified')
   continue
  if isinstance(n,(ast.Assign,ast.AnnAssign)):
   try:ast.literal_eval(n.value)
   except (ValueError,TypeError):raise ValueError('New module assignments must be passive constants') from None
   continue
  raise ValueError('New module import-time effects require separate qualification')
def header_effects(node):
 annotations=[a.annotation for a in [*node.args.posonlyargs,*node.args.args,*node.args.kwonlyargs] if a.annotation]
 for variadic in (node.args.vararg,node.args.kwarg):
  if variadic and variadic.annotation:annotations.append(variadic.annotation)
 expressions=[*node.args.defaults,*[v for v in node.args.kw_defaults if v],*annotations]
 if node.returns:expressions.append(node.returns)
 return bool(node.decorator_list) or any(isinstance(v,ast.Call) for expression in expressions for v in ast.walk(expression))
def headers(raw):
 result={}
 for node in ast.parse(raw).body:
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):result[node.name]=node
  elif isinstance(node,ast.ClassDef):
   for fn in node.body:
    if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):result[node.name+'.'+fn.name]=fn
 return result
def passive_structure(raw):
 tree=ast.parse(raw);nodes=[]
 for node in tree.body:
  if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.Import,ast.ImportFrom)):continue
  if isinstance(node,ast.ClassDef):node.body=[n for n in node.body if not isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
  nodes.append(ast.dump(node,include_attributes=False))
 return nodes
def inspect(previous,candidate,manifest):
 previous,candidate=Path(previous),Path(candidate);old=files(previous);new=files(candidate)
 if manifest.get('version')!=VERSION or manifest.get('files')!=old or not re.fullmatch('[a-f0-9]{40}',manifest.get('source_revision','')):raise ValueError('Installed supervisor predecessor identity differs')
 changed=sorted(n for n in set(old)|set(new) if old.get(n)!=new.get(n))
 if not changed:raise ValueError('No operational supervisor source change')
 for name in changed:
  if name in KERNEL or name not in new or Path(name).suffix!='.py':raise ValueError('Frozen supervisor authority/transport broker or source deletion requires separate qualification: '+name)
  raw=(candidate/name).read_bytes()
  if name not in old:declarations(raw)
  else:
   if passive_structure((previous/name).read_bytes())!=passive_structure(raw):raise ValueError('Changed module-level execution requires separate qualification')
   a,b=definitions((previous/name).read_bytes()),definitions(raw)
   for fn,node in headers(raw).items():
    if a.get(fn)!=b[fn] and header_effects(node):raise ValueError('Changed function import-time effects require separate qualification')
   for fn in METHODS.get(name,set()):
    if fn not in a or a[fn]!=b.get(fn):raise ValueError('Frozen supervisor admission/qualification method changed: '+name+':'+fn)
  if name.startswith('capability_'):
   import importlib.util
   spec=importlib.util.spec_from_file_location('trusted_capability_contract',previous/'capabilities.py')
   module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
   module.descriptor(raw,name)
 for path in (previous/'tests').glob('*.py'):
  proposed=candidate/'tests'/path.name
  if not proposed.is_file() or proposed.is_symlink() or proposed.read_bytes()!=path.read_bytes():raise ValueError('Existing supervisor checks changed')
 paths={'platform_supervisor/'+n:new[n] for n in changed}
 for p in (candidate/'tests').glob('*.py'):
  if not (previous/'tests'/p.name).exists():
   if p.is_symlink():raise ValueError('New supervisor checks cannot be links')
   paths['platform_supervisor/tests/'+p.name]=digest(p.read_bytes())
 return dict(version=VERSION,previous_revision=manifest['source_revision'],previous_files=old,files=new,changed_files=changed,candidate_paths=paths,
  source_binding=digest(encoded(new)),existing_checks_unchanged=True,authority_and_transport_unchanged=True,
  scientific_completion=False)
