#!/usr/bin/env bash
# Trusted initial installation on the existing subscription host. No replacement,
# login flow, static AWS keys or experiment launch is performed.
set -eu
test "$(id -u)" = 0
test "$#" = 5 || test "$#" = 6 || test "$#" = 7
bundle_sha="$1"
image_sha="$2"
image_archive_sha="$3"
secret_arn="$4"
bucket="$5"
image_source="${6:-archive}"
qualification_bundle="${7:-$bundle_sha}"
[[ "$bundle_sha" =~ ^[a-f0-9]{64}$ ]]
[[ "$image_sha" =~ ^sha256:[a-f0-9]{64}$ ]]
[[ "$image_archive_sha" =~ ^[a-f0-9]{64}$ ]]
[[ "$qualification_bundle" =~ ^[a-f0-9]{64}$ ]]
[[ "$secret_arn" =~ ^arn:aws:secretsmanager:us-east-1:395567831870:secret:jumpserve/platform-supervisor-[A-Za-z0-9]+$ ]]
test "$bucket" = cdk-hnb659fds-assets-395567831870-us-east-1
test "$(aws sts get-caller-identity --query Account --output text --region us-east-1)" = 395567831870
systemctl is-active --quiet docker
mkdir -p /var/lib/jumpserve-platform/install /opt/jumpserve/platform-releases
release="/opt/jumpserve/platform-releases/$bundle_sha"
archive="/var/lib/jumpserve-platform/install/$image_archive_sha.tar.gz"
if test "$image_source" = qualified-host; then
 python3.12 - "$qualification_bundle" "$image_sha" <<'PY'
import json,pathlib,sys
bundle,image=sys.argv[1:];root=pathlib.Path('/var/lib/jumpserve-platform-bootstrap')/bundle
report=json.loads((root/'report.json').read_bytes())
assert report['passed'] is True and report['live'] is True and report['bundle_sha256']==bundle and report['image']==image
assert 0<report['actual_provider_calls']<=6 and report['existing_test_unchanged'] and report['container_check_passed']
PY
else
 test "$image_source" = archive
 aws s3 cp "s3://$bucket/platform-supervisor/images/$image_archive_sha.tar.gz" "$archive" --region us-east-1 --only-show-errors
 echo "$image_archive_sha  $archive" | sha256sum --check
 docker load --input "$archive" >/dev/null
fi
docker image inspect "$image_sha" >/dev/null
mkdir -p "$release"
python3.12 - "$bundle_sha" "$release" <<'PY'
import hashlib, pathlib, stat, sys, zipfile
sha,destination=sys.argv[1:];path=pathlib.Path('/tmp/jumpserve-platform-'+sha+'.zip');raw=path.read_bytes()
assert hashlib.sha256(raw).hexdigest()==sha
with zipfile.ZipFile(path) as archive:
 for item in archive.infolist():
  name=item.filename
  assert name in ('jumpserve-platform.service','install-platform.sh','qualify-platform-host.py','reconcile-platform-host.py','Dockerfile') or name.startswith('platform_supervisor/') and name.count('/')==1 and pathlib.Path(name).suffix in ('.py','.json')
  assert not name.startswith('/') and '..' not in pathlib.Path(name).parts and not stat.S_ISLNK(item.external_attr>>16)
  target=pathlib.Path(destination)/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.read(item));target.chmod(0o644)
PY
python3.12 - "$image_sha" "$secret_arn" <<'PY'
import os,pathlib,re,sys
values={}
for line in pathlib.Path('/etc/jumpserve-openclaw.env').read_text().splitlines():
 if '=' in line:
  key,value=line.split('=',1);values[key]=value.strip("'\"")
supabase=values['SUPABASE_SECRET_ARN'];builder=values['OPENCLAW_BUILDER_PACKAGE']
assert re.fullmatch(r'arn:aws:secretsmanager:us-east-1:395567831870:secret:jumpserve/supabase-service-key(?:-[A-Za-z0-9]{6})?',supabase)
assert re.fullmatch(r'/opt/jumpserve/builder-vendor/[a-f0-9]{64}/node_modules/openclaw',builder)
assert pathlib.Path(builder,'openclaw.mjs').is_file()
env=dict(SUPABASE_SECRET_ARN=supabase,PLATFORM_SECRET_ARN=sys.argv[2],PLATFORM_IMAGE=sys.argv[1],PLATFORM_SPOOL='/var/lib/jumpserve-platform',OPENCLAW_BUILDER_PACKAGE=builder,AWS_DEFAULT_REGION='us-east-1')
path=pathlib.Path('/etc/jumpserve-platform.env');path.write_text(''.join(k+'='+v+'\n' for k,v in env.items()));path.chmod(0o600)
PY
if test -e /opt/jumpserve/platform && ! test -L /opt/jumpserve/platform; then
  echo 'Existing unversioned platform directory needs explicit reconciliation.' >&2
  exit 1
fi
chown -R jumpserve:jumpserve /var/lib/jumpserve-platform
chmod 700 /var/lib/jumpserve-platform
ln -sfn "$release" /opt/jumpserve/platform
install -m 644 "$release/jumpserve-platform.service" /etc/systemd/system/jumpserve-platform.service
systemctl daemon-reload
systemctl enable --now jumpserve-platform.service
printf '{"installed":true,"worker_replaced":false,"research_service_restarted":false,"aws_static_keys":false}\n'
