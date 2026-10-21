#!/bin/bash
set -eu
umask 077
cd /opt/jumpserve
curl --fail --silent --show-error --location https://nodejs.org/dist/v24.16.0/node-v24.16.0-linux-x64.tar.xz -o node.tar.xz
echo 'd804845d34eddc21dc1092b519d643ef40b1f58ec5dec5c22b1f4bd8fabde6c9  node.tar.xz' | sha256sum --check
mkdir -p node openclaw
tar -xJf node.tar.xz --strip-components=1 -C node
cp dependencies/package.json dependencies/package-lock.json openclaw/
export PATH=/opt/jumpserve/node/bin:/usr/bin:/bin
cd openclaw
npm ci --omit=dev --no-audit --no-fund
cd /opt/jumpserve
python3.12 - <<'PY'
from pathlib import Path
import hashlib,json
root=Path('/opt/jumpserve');patch=json.loads((root/'dependencies/auth-patch.json').read_bytes());path=root/'openclaw/node_modules/openclaw'/patch['path'];raw=path.read_bytes()
assert hashlib.sha256(raw).hexdigest()==patch['original_sha256'] and raw.count(patch['before'].encode())==1
path.with_suffix(path.suffix+'.original').write_bytes(raw)
corrected=raw.replace(patch['before'].encode(),patch['after'].encode());assert hashlib.sha256(corrected).hexdigest()==patch['corrected_sha256'];path.write_bytes(corrected)
PY
python3.12 -m venv python
python/bin/pip install --disable-pip-version-check -r dependencies/requirements.txt
python/bin/pip freeze > dependencies/installed-python.txt
node/bin/node --version > dependencies/installed-node.txt
chmod -R a+rX /opt/jumpserve
cat > /var/lib/jumpserve-openclaw/auth/config.json <<'JSON'
{"agents":{"defaults":{"model":{"primary":"openai/gpt-6.1-sol","fallbacks":[]}}},"plugins":{"allow":["openai"]},"tools":{"deny":["*"],"toolSearch":false,"codeMode":false}}
JSON
chmod 600 /var/lib/jumpserve-openclaw/auth/config.json
