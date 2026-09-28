#!/usr/bin/env bash
# SHARD, SHARDS and FILE_HASHES_JSON are supplied in EC2 user data by the launcher.
set -euo pipefail
readonly BUCKET=jumpserve-nines2026-395567831870-us-east-1
readonly CAMPAIGN=nines2026-balanced-v1
readonly WORK=/opt/jumpserve-worker
mkdir -p "$WORK"
exec > >(tee -a "$WORK/worker.log") 2>&1
export SHARD SHARDS FILE_HASHES_JSON

finish() {
  local code=$?
  trap - EXIT
  set +e
  python3 - <<'PY'
import boto3, os
from pathlib import Path
s3 = boto3.client('s3', region_name='us-east-1')
root = Path('/opt/jumpserve-worker')
for path in [root/'worker.log', *list((root/'preflight').rglob('*'))]:
    if path.is_file():
        s3.upload_file(str(path), 'jumpserve-nines2026-395567831870-us-east-1',
                      'campaigns/nines2026-balanced-v1/worker-'+os.environ['SHARD']+'/'+str(path.relative_to(root)))
PY
  echo "Worker exit status: $code"
  sync
  shutdown -h now
  exit "$code"
}
trap finish EXIT

# Replace the builder deadline; EC2 shutdown behavior is set to terminate.
cat >/etc/systemd/system/jumpserve-research-deadline.timer <<'UNIT'
[Unit]
Description=Terminate the NINeS research worker after six hours
[Timer]
OnBootSec=6h
Unit=jumpserve-research-deadline.service
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl restart jumpserve-research-deadline.timer
systemctl stop apt-daily.timer apt-daily-upgrade.timer

python3 - <<'PY'
import boto3, hashlib, json, os
from pathlib import Path
s3 = boto3.client('s3', region_name='us-east-1')
root = Path('/opt/jumpserve-worker')
for name, expected in json.loads(os.environ['FILE_HASHES_JSON']).items():
    if '/' in name or name.startswith('.'):
        raise ValueError('Invalid research artifact name')
    target = root/name
    s3.download_file('jumpserve-nines2026-395567831870-us-east-1', 'code/v1/'+name, str(target))
    if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        raise ValueError('Research artifact hash mismatch: '+name)
PY
python3 "$WORK/preflight.py" --output "$WORK/preflight" --expected-cpus 2
python3 - <<'PY'
import boto3, os
from pathlib import Path
root = Path('/opt/jumpserve-worker/preflight')
s3 = boto3.client('s3', region_name='us-east-1')
for path in root.rglob('*'):
    if path.is_file():
        s3.upload_file(str(path), 'jumpserve-nines2026-395567831870-us-east-1',
                      'campaigns/nines2026-balanced-v1/worker-'+os.environ['SHARD']+'/preflight/'+str(path.relative_to(root)))
PY
python3 "$WORK/runner.py" --manifest "$WORK/campaign-v1.json" \
  --output "$WORK/worker-$SHARD" --shard "$SHARD" --shards "$SHARDS" --bucket "$BUCKET"
