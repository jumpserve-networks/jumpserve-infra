#!/usr/bin/env python3
"""Build reviewable user data and a source hash manifest; makes no AWS calls."""
import hashlib
import json
from pathlib import Path
import shlex

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]/'jumpserve-back-end'/'experiments'/'nines2026_delay_equalization'
FILES = ['runner.py', 'preflight.py', 'campaign-v1.json', 'PROTOCOL.md']
hashes = {name: hashlib.sha256((BACKEND/name).read_bytes()).hexdigest() for name in FILES}
(HERE/'artifact-hashes.json').write_text(json.dumps(hashes, indent=2)+'\n')
body = (HERE/'worker.sh').read_text().split('\n', 1)[1]
generated = HERE/'generated'
generated.mkdir(exist_ok=True)
for shard in range(8):
    content = '#!/usr/bin/env bash\n'+f'SHARD={shard}\nSHARDS=8\nFILE_HASHES_JSON='+shlex.quote(json.dumps(hashes))+'\n'+body
    (generated/f'worker-{shard}.sh').write_text(content)
print(json.dumps({'artifacts': hashes, 'workers': 8}, indent=2))
