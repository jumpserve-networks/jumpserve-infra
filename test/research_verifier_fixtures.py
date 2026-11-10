"""Synthetic byte and identity fixtures for production-verifier units."""
import hashlib
import io
import json
import uuid
import zipfile

def digest(raw): return hashlib.sha256(raw).hexdigest()

def canonical(value): return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def identity(name): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'continuation-unit:' + name))

def archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as output:
        for name, raw in sorted(files.items()): output.writestr(name, raw)
    return buffer.getvalue()
