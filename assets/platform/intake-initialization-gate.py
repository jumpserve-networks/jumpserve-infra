"""Qualify only the exact fresh-intake marker correction; never arbitrary intake edits."""
import ast
import hashlib
import json
from pathlib import Path

VERSION='intake-initialization-repair-v1'


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def shape(node):return ast.dump(node,include_attributes=False)


def normalized(raw,corrected=False):
 tree=ast.parse(raw)
 functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='intake']
 if len(functions)!=1:raise ValueError('One original intake initializer required.')
 function=functions[0]
 old=ast.parse('not context',mode='eval').body
 new=ast.parse("not context or context=={'intake_pool_version':'warm-intake-v1'}",mode='eval').body
 before=ast.parse("context=sources.original(study,task['actor_id'])").body[0]
 after=ast.parse("context=dict(context,**sources.original(study,task['actor_id']))").body[0]
 guards=[node for node in function.body if isinstance(node,ast.If) and shape(node.test)==shape(new if corrected else old)]
 if len(guards)!=1:raise ValueError('Exact original fresh-intake guard required.')
 assignments=[node for node in guards[0].body if isinstance(node,ast.Assign) and shape(node)==shape(after if corrected else before)]
 if len(assignments)!=1:raise ValueError('Exact source initialization and routing preservation required.')
 if corrected:
  guards[0].test=old
  index=guards[0].body.index(assignments[0]);guards[0].body[index]=before
 return shape(tree)


def read(root,name):
 root=Path(root);path=root/name
 if Path(name).is_absolute() or '..' in Path(name).parts or root.is_symlink() or any(p.is_symlink() for p in [path,*path.parents] if p.is_relative_to(root)):
  raise ValueError('Plain source paths required.')
 if not path.is_file():raise ValueError('Declared source is missing: '+name)
 return path.read_bytes()


def inspect(previous,candidate,manifest):
 if manifest.get('version')!='warm-intake-v1' or not manifest.get('files') or digest(canonical(manifest['files']))!=manifest.get('source_binding'):
  raise ValueError('Exact original warm-intake manifest required.')
 previous,candidate=Path(previous),Path(candidate);files={};changed=[]
 for name,expected in manifest['files'].items():
  old,new=read(previous,name),read(candidate,name)
  if digest(old)!=expected:raise ValueError('Original intake source hash differs: '+name)
  files[name]=digest(new)
  if old==new:continue
  if name!='autonomy.py' or normalized(old)!=normalized(new,corrected=True):
   raise ValueError('Only the exact intake initialization correction is qualified: '+name)
  changed.append(name)
 if changed!=['autonomy.py']:raise ValueError('Exact intake initializer correction required.')
 tests=previous/'tests'
 if not tests.is_dir() or tests.is_symlink():raise ValueError('Retained original research tests required.')
 count=0
 for path in tests.rglob('*.py'):
  name=path.relative_to(previous).as_posix()
  if read(previous,name)!=read(candidate,name):raise ValueError('Existing research validation changed: '+name)
  count+=1
 if not count:raise ValueError('Original research regressions are missing.')
 return dict(version=VERSION,previous_source_revision=manifest['source_revision'],previous_source_binding=manifest['source_binding'],
  files=files,source_binding=digest(canonical(files)),changed_files=changed,existing_tests_unchanged=True,
  scientific_and_request_content_unchanged=True,provider_calls=0)
