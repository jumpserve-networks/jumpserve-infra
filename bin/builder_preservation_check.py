"""Verify equivalent lossless metadata representations without trusting notes."""
import base64
import binascii
import hashlib
import json

def proof(raw, original):
    if len(raw)>256000: return None
    sha=hashlib.sha256(original).hexdigest()
    representation_sha=hashlib.sha256(raw).hexdigest()
    if raw==original: return dict(encoding='identity',sha256=sha,representation_sha256=representation_sha,bytes=len(original))
    try:
        value=json.loads(raw)
        if not isinstance(value,dict) or value.get('original_sha256')!=sha or not isinstance(value.get('original_bytes_base64'),str): return None
        decoded=base64.b64decode(value['original_bytes_base64'],validate=True)
        if decoded!=original or hashlib.sha256(decoded).hexdigest()!=sha:return None
        return dict(encoding='json-base64-sha256',sha256=sha,representation_sha256=representation_sha,bytes=len(decoded))
    except (ValueError,TypeError,binascii.Error):return None
