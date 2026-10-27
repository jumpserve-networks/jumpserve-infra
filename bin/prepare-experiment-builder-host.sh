#!/bin/bash
# Explicit release prerequisite; never invoked by routine local verification.
# Run through the existing audited SSM release path after account verification.
set -euo pipefail
umask 077
test "$(aws sts get-caller-identity --query Account --output text)" = '395567831870'
test "$(id -u)" = '0'
grep -Fxq 'SUPABASE_URL=https://regphejnlvfpyokpniny.supabase.co' /etc/jumpserve-openclaw.env
test -n "${JUMPSERVE_BUILDER_IMAGE:-}"
if [[ ! "$JUMPSERVE_BUILDER_IMAGE" =~ ^([a-zA-Z0-9][a-zA-Z0-9./:_-]*@)?sha256:[a-f0-9]{64}$ ]]; then
  echo 'A reviewed image pinned by immutable repository digest is required.' >&2
  exit 1
fi
dnf install -y docker
systemctl enable --now docker
usermod -aG docker jumpserve
if [[ "$JUMPSERVE_BUILDER_IMAGE" != sha256:* ]]; then docker pull "$JUMPSERVE_BUILDER_IMAGE"; fi
docker image inspect "$JUMPSERVE_BUILDER_IMAGE" --format '{{.Id}} {{.Os}} {{.Architecture}}'
test "$(docker image inspect "$JUMPSERVE_BUILDER_IMAGE" --format '{{.Os}}/{{.Architecture}}')" = 'linux/amd64'
BUILDER_WORKER_IDS="$(id -u jumpserve):$(id -g jumpserve)"
test "$(docker run --rm --network none --user "$BUILDER_WORKER_IDS" --security-opt no-new-privileges=false "$JUMPSERVE_BUILDER_IMAGE" sudo -n id -u)" = '0'
# Require the evaluated prompt/cost policy before writing activation settings.
set -a
. /etc/jumpserve-openclaw.env
set +a
/opt/jumpserve/python/bin/python -B - <<'PY'
import datetime as dt,json,pathlib,sys
sys.path.insert(0,'/opt/jumpserve/runtime')
import store
from workflow import digest
active=store.request('/rest/v1/rpc/get_active_agent_prompt?p_module_id=research-experiment-builder')
assert len(active)==1 and active[0]['id']=='dfab5ecb-b8b9-5ad3-8771-f28a06b53b27' and active[0]['published_at']
assert active[0]['version']=='research-experiment-builder-v2'
policy=json.loads(pathlib.Path('/opt/jumpserve/runtime/policies/built-package-costs-v2.json').read_bytes())
assert policy['approved_for_lab_execution'] and policy['maximum_cents']==1000
assert dt.datetime.now(dt.timezone.utc)<dt.datetime.fromisoformat(policy['valid_until'].replace('Z','+00:00'))
assert digest(pathlib.Path('/opt/jumpserve/runtime/generated_package.py').read_bytes())==policy['wrapper_sha256']
assert not store.request('/rest/v1/research_model_dispatches?status=in.(queued,running)&select=id&limit=1'),'Drain active model dispatches before release.'
PY
# Preserve the installed upstream package and its ChatGPT grant. Only the
# builder uses this separately versioned correction, never the data-only agent.
BUILDER_PACKAGE_PATH="$(/opt/jumpserve/python/bin/python -B - <<'PY'
import hashlib,json,os,pathlib,shutil
patch=json.loads(pathlib.Path('/opt/jumpserve/runtime/openclaw-builder-patch.json').read_bytes())
source=pathlib.Path('/opt/jumpserve/openclaw/node_modules/openclaw')
original=(source/patch['path']).read_bytes();assert hashlib.sha256(original).hexdigest()==patch['original_sha256']
base=pathlib.Path('/opt/jumpserve/builder-vendor')/patch['corrected_sha256'];parent=base/'node_modules';dest=parent/'openclaw'
for directory in (base.parent,base,parent):directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o755)
if not dest.exists():
 shutil.copytree(source,dest,copy_function=os.link,symlinks=True)
 for item in source.parent.iterdir():
  if item.name!='openclaw' and not (parent/item.name).exists():(parent/item.name).symlink_to(item,target_is_directory=item.is_dir())
target=dest/patch['path'];corrected=original.replace(patch['before'].encode(),patch['after'].encode())
assert hashlib.sha256(corrected).hexdigest()==patch['corrected_sha256']
assert hashlib.sha256(target.read_bytes()).hexdigest() in (patch['original_sha256'],patch['corrected_sha256'])
if target.read_bytes()!=corrected:
 temporary=target.with_suffix('.builder-correction');temporary.write_bytes(corrected);temporary.chmod(0o644);temporary.replace(target)
assert (source/patch['path']).read_bytes()==original
(base/'upstream-original.mjs').write_bytes(original)
(base/'patch-receipt.json').write_text(json.dumps(patch,indent=2)+'\n')
# Do not chown hardlinks recursively: that would change upstream metadata.
print(dest)
PY
)"
# The model bridge remains loopback-only and auth stays in its existing store.
# Generated commands receive only the workspace mount, never this env file.
sed -i '/^OPENCLAW_BUILDER_IMAGE=/d;/^OPENCLAW_BUILDER_PACKAGE=/d;/^RESEARCH_BUILDER_ENABLED=/d' /etc/jumpserve-openclaw.env
printf '%s\n' "OPENCLAW_BUILDER_IMAGE=$JUMPSERVE_BUILDER_IMAGE" "OPENCLAW_BUILDER_PACKAGE=$BUILDER_PACKAGE_PATH" 'RESEARCH_BUILDER_ENABLED=true' >> /etc/jumpserve-openclaw.env
chmod 600 /etc/jumpserve-openclaw.env
# Restart/health verification and actual tool/prompt checks belong to the
# explicit release procedure; this script does not activate paper admission.
